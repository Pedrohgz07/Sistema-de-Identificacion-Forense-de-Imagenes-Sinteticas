import os
import numpy as np
import pandas as pd
import tensorflow as tf
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.metrics import (
    confusion_matrix,
    classification_report,
    roc_curve,
    auc,
    f1_score
)

from tensorflow.keras import layers, Model
from tensorflow.keras.applications import EfficientNetB0
from tensorflow.keras.callbacks import ( EarlyStopping, ModelCheckpoint, ReduceLROnPlateau)

tf.random.set_seed(42)
np.random.seed(42)

IMG_SIZE    = (224, 224)
BATCH_SIZE  = 32

EPOCHS_P1   = 10
EPOCHS_P2   = 15

LR_P1       = 1e-3
LR_P2       = 1e-5

UNFREEZE    = 30

AUTOTUNE    = tf.data.AUTOTUNE

CLASS_NAMES = ["real", "fake"]

print("TensorFlow:", tf.__version__)
print("GPUs disponibles:", tf.config.list_physical_devices("GPU"))

gpus = tf.config.list_physical_devices("GPU")

strategy = (
    tf.distribute.MirroredStrategy()
    if len(gpus) > 1
    else tf.distribute.get_strategy()
)

print(
    f"Estrategia: {strategy.__class__.__name__}"
    f" | Réplicas: {strategy.num_replicas_in_sync}"
)
BASE = "/kaggle/input/140k-real-and-fake-faces/real_vs_fake/real-vs-fake"

print("\nCargando CSVs...")

train_df = pd.read_csv(f"{BASE}/train.csv")
val_df   = pd.read_csv(f"{BASE}/valid.csv")
test_df  = pd.read_csv(f"{BASE}/test.csv")

print("Columnas originales del CSV:", train_df.columns.tolist())

train_df["filepath"] = train_df["path"].apply(lambda p: os.path.join(BASE, p))
val_df["filepath"]   = val_df["path"].apply(lambda p: os.path.join(BASE, p))
test_df["filepath"]  = test_df["path"].apply(lambda p: os.path.join(BASE, p))

print("Train:", len(train_df))
print("Val:",   len(val_df))
print("Test:",  len(test_df))

print("Ejemplo ruta:", train_df.iloc[0]["filepath"])
print("Existe:", os.path.exists(train_df.iloc[0]["filepath"]))
print("Distribución de labels en train (según CSV original):\n", train_df["label"].value_counts())

def load_image(path, label):
    image = tf.io.read_file(path)
    image = tf.image.decode_jpeg(image, channels=3)
    image = tf.image.resize(image, IMG_SIZE)
    image = tf.cast(image, tf.float32)
    return image, label

def dataframe_to_dataset(df, shuffle=False):
    ds = tf.data.Dataset.from_tensor_slices(
        (
            df["filepath"].values,
            df["label"].values.astype(np.float32)
        )
    )

    if shuffle:
        ds = ds.shuffle(min(len(df), 10000), seed=42)

    ds = (
        ds
        .map(load_image, num_parallel_calls=AUTOTUNE)
        .batch(BATCH_SIZE)
        .prefetch(AUTOTUNE)
    )
    return ds

train_ds = dataframe_to_dataset(train_df, shuffle=True)
val_ds   = dataframe_to_dataset(val_df)
test_ds  = dataframe_to_dataset(test_df)

def build_model():
    base_model = EfficientNetB0(
        include_top=False,
        weights="imagenet",
        input_shape=(*IMG_SIZE, 3)
    )
    base_model.trainable = False

    inputs = tf.keras.Input(shape=(*IMG_SIZE, 3))

    x = layers.RandomFlip("horizontal")(inputs)
    x = layers.RandomRotation(0.05)(x)
    x = layers.RandomZoom(0.1)(x)

    x = base_model(x)

    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dense(128, activation="relu")(x)
    x = layers.Dropout(0.3)(x)
    outputs = layers.Dense(1, activation="sigmoid")(x)

    model = Model(inputs, outputs, name="ForensicAI_Classifier")
    return model, base_model

with strategy.scope():
    model, base_model = build_model()

model.summary()

with strategy.scope():
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=LR_P1),
        loss="binary_crossentropy",
        metrics=[
            "accuracy",
            tf.keras.metrics.AUC(name="auc")
        ]
    )

callbacks_p1 = [
    EarlyStopping(
        monitor="val_loss",
        patience=3,
        mode="min",
        restore_best_weights=True
    ),
    ModelCheckpoint(
        "best_model_p1.keras",
        monitor="val_loss",
        save_best_only=True,
        mode="min"
    ),
    ReduceLROnPlateau(
        monitor="val_loss",
        factor=0.5,
        patience=2,
        min_lr=1e-6
    )
]

print("\n── Fase 1: Entrenando cabeza ──")
history1 = model.fit(
    train_ds,
    validation_data=val_ds,
    epochs=EPOCHS_P1,
    callbacks=callbacks_p1
)

epocas_fase1 = len(history1.history["loss"])

base_model.trainable = True
for layer in base_model.layers[:-UNFREEZE]:
    layer.trainable = False

with strategy.scope():
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=LR_P2),
        loss="binary_crossentropy",
        metrics=[
            "accuracy",
            tf.keras.metrics.AUC(name="auc")
        ]
    )

callbacks_p2 = [
    EarlyStopping(
        monitor="val_auc",
        patience=5,
        mode="max",
        restore_best_weights=True
    ),
    ModelCheckpoint(
        "best_model_final.keras",
        monitor="val_auc",
        save_best_only=True,
        mode="max"
    ),
    ReduceLROnPlateau(
        monitor="val_loss",
        factor=0.5,
        patience=2,
        min_lr=1e-7
    )
]

print("\n── Fase 2: Fine-tuning ──")
history2 = model.fit(
    train_ds,
    validation_data=val_ds,
    epochs=epocas_fase1 + EPOCHS_P2,
    initial_epoch=epocas_fase1,
    callbacks=callbacks_p2
)

loss, acc, auc_score = model.evaluate(test_ds, verbose=1)
print(f"\nTest Loss:     {loss:.4f}")
print(f"Test Accuracy: {acc*100:.2f}%")
print(f"Test AUC:      {auc_score:.4f}")

y_true       = test_df["label"].values.astype(int)
y_pred_prob  = model.predict(test_ds, verbose=1).flatten()

print("\nBuscando umbral óptimo sobre val set...")

y_val_true    = val_df["label"].values.astype(int)
y_val_prob    = model.predict(val_ds, verbose=0).flatten()

umbrales      = np.arange(0.30, 0.71, 0.01)
f1_scores     = [f1_score(y_val_true, (y_val_prob > t).astype(int)) for t in umbrales]
umbral_optimo = float(umbrales[np.argmax(f1_scores)])

print(f"Umbral óptimo (F1 máximo): {umbral_optimo:.2f}  →  F1 = {max(f1_scores):.4f}")

y_pred = (y_pred_prob > umbral_optimo).astype(int)

def plot_history(h1, h2, metric, ax):
    v1  = h1.history[metric]     + h2.history[metric]
    vv1 = h1.history[f"val_{metric}"] + h2.history[f"val_{metric}"]
    sep = len(h1.history[metric])
    epochs = range(1, len(v1) + 1)

    ax.plot(epochs, v1,  label=f"Train {metric}")
    ax.plot(epochs, vv1, label=f"Val {metric}")
    ax.axvline(sep, color="gray", linestyle="--", label="Inicio fase 2")
    ax.set_xlabel("Época")
    ax.set_ylabel(metric.capitalize())
    ax.set_title(f"Curva de {metric.capitalize()}")
    ax.legend()

fig, axes = plt.subplots(2, 2, figsize=(14, 10))

plot_history(history1, history2, "loss",     axes[0, 0])
plot_history(history1, history2, "accuracy", axes[0, 1])

cm = confusion_matrix(y_true, y_pred)
sns.heatmap(
    cm,
    annot=True,
    fmt="d",
    cmap="Blues",
    ax=axes[1, 0],
    xticklabels=CLASS_NAMES,
    yticklabels=CLASS_NAMES
)
axes[1, 0].set_title(f"Matriz de Confusión (umbral={umbral_optimo:.2f})")
axes[1, 0].set_ylabel("Real")
axes[1, 0].set_xlabel("Predicho")

fpr, tpr, _ = roc_curve(y_true, y_pred_prob)
roc_auc = auc(fpr, tpr)
axes[1, 1].plot(fpr, tpr, color="#534AB7", lw=2, label=f"AUC = {roc_auc:.4f}")
axes[1, 1].plot([0, 1], [0, 1], "k--", lw=1)
axes[1, 1].set_xlabel("False Positive Rate")
axes[1, 1].set_ylabel("True Positive Rate")
axes[1, 1].set_title("Curva ROC")
axes[1, 1].legend(loc="lower right")

plt.tight_layout()
plt.savefig("resultados_evaluacion.png", dpi=150)
plt.show()

print("\nReporte de clasificación:")
print(classification_report(y_true, y_pred, target_names=CLASS_NAMES))

import json
with open("umbral_optimo.json", "w") as f:
    json.dump({"DECISION_THRESHOLD": umbral_optimo}, f, indent=2)
print(f"Umbral guardado en umbral_optimo.json: {umbral_optimo:.2f}")

model.save("modelo_ai_vs_real.keras")
print("Modelo guardado correctamente.")

