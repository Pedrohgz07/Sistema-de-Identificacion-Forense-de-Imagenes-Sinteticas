import os
import json
import numpy as np
import pandas as pd
import tensorflow as tf
import matplotlib.pyplot as plt
import seaborn as sns
from tensorflow.keras import layers, models
from tensorflow.keras.applications import EfficientNetB0
from tensorflow.keras.callbacks import ModelCheckpoint, EarlyStopping, ReduceLROnPlateau
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.utils.class_weight import compute_class_weight


IMG_SIZE = 224
BATCH_SIZE = 32
EPOCHS_FASE1 = 20
EPOCHS_FASE2 = 10
DATASET_DIR = "C:/Users/usuario/Documents/dataset"


def cargar_datasets():
    train_ds = tf.keras.utils.image_dataset_from_directory(
        os.path.join(DATASET_DIR, 'train'),
        image_size=(IMG_SIZE, IMG_SIZE),
        batch_size=BATCH_SIZE,
        label_mode='binary',
        shuffle=True,
        seed=42
    )
    val_ds = tf.keras.utils.image_dataset_from_directory(
        os.path.join(DATASET_DIR, 'val'),
        image_size=(IMG_SIZE, IMG_SIZE),
        batch_size=BATCH_SIZE,
        label_mode='binary',
        shuffle=False
    )
    test_ds = tf.keras.utils.image_dataset_from_directory(
        os.path.join(DATASET_DIR, 'test'),
        image_size=(IMG_SIZE, IMG_SIZE),
        batch_size=BATCH_SIZE,
        label_mode='binary',
        shuffle=False
    )
    return train_ds, val_ds, test_ds


def verificar_orden_clases(class_names):
    assert class_names[0].lower() in ['real', 'reales'], (
        f"Orden de clases inesperado: {class_names}. "
        f"Se esperaba índice 0 = 'Real'."
    )


def calcular_class_weights(train_ds):
    y_train = np.concatenate([y for x, y in train_ds], axis=0).flatten()
    pesos = compute_class_weight(
        class_weight='balanced',
        classes=np.unique(y_train),
        y=y_train
    )
    return {i: pesos[i] for i in range(len(pesos))}


def preparar_pipeline(train_ds, val_ds, test_ds):
    autotune = tf.data.AUTOTUNE
    train_ds = train_ds.cache().prefetch(buffer_size=autotune)
    val_ds = val_ds.cache().prefetch(buffer_size=autotune)
    test_ds = test_ds.cache().prefetch(buffer_size=autotune)
    return train_ds, val_ds, test_ds


def construir_modelo():
    data_augmentation = tf.keras.Sequential([
        layers.RandomFlip("horizontal"),
        layers.RandomRotation(0.1),
        layers.RandomZoom(0.1),
    ])
    base_model = EfficientNetB0(
        weights='imagenet',
        include_top=False,
        input_shape=(IMG_SIZE, IMG_SIZE, 3)
    )
    base_model.trainable = False

    inputs = layers.Input(shape=(IMG_SIZE, IMG_SIZE, 3))
    x = data_augmentation(inputs)
    x = base_model(x, training=False)
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(0.3)(x)
    outputs = layers.Dense(1, activation='sigmoid')(x)

    model = models.Model(inputs, outputs)
    return model, base_model


def compilar_modelo(model, learning_rate):
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss='binary_crossentropy',
        metrics=['accuracy', tf.keras.metrics.AUC(name='auc')]
    )


def crear_callbacks(nombre_checkpoint):
    return [
        ModelCheckpoint(
            nombre_checkpoint,
            monitor='val_auc',
            mode='max',
            save_best_only=True,
            verbose=1
        ),
        EarlyStopping(
            monitor='val_auc',
            mode='max',
            patience=5,
            restore_best_weights=True,
            verbose=1
        ),
        ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.2,
            patience=3,
            verbose=1
        )
    ]


def descongelar_ultimas_capas(base_model, n_capas=20):
    base_model.trainable = True
    for layer in base_model.layers[:-n_capas]:
        layer.trainable = False


def graficar_historial(history_fase1, history_fase2):
    metrics = ['loss', 'accuracy', 'auc']
    df1 = pd.DataFrame(history_fase1.history)
    df2 = pd.DataFrame(history_fase2.history)
    df2.index += len(df1)
    df = pd.concat([df1, df2])

    fig, axes = plt.subplots(1, len(metrics), figsize=(18, 5))
    for ax, metric in zip(axes, metrics):
        ax.plot(df.index, df[metric], label='train')
        ax.plot(df.index, df[f'val_{metric}'], label='val')
        ax.axvline(len(df1) - 1, color='gray', linestyle='--', alpha=0.5)
        ax.set_title(metric.upper())
        ax.set_xlabel('Época')
        ax.legend()

    plt.tight_layout()
    plt.savefig('historial_entrenamiento.png', dpi=150)
    plt.close()

    df.to_csv('historial_entrenamiento.csv', index_label='epoca')


def graficar_matriz_confusion(y_true, y_pred, class_names, threshold, nombre_archivo):
    matriz = confusion_matrix(y_true, y_pred)
    plt.figure(figsize=(6, 5))
    sns.heatmap(
        matriz,
        annot=True,
        fmt='d',
        cmap='Blues',
        xticklabels=class_names,
        yticklabels=class_names
    )
    plt.title(f'Matriz de confusión (threshold={threshold:.2f})')
    plt.xlabel('Predicción')
    plt.ylabel('Real')
    plt.tight_layout()
    plt.savefig(nombre_archivo, dpi=150)
    plt.close()


def calcular_umbral_optimo(model, val_ds):
    y_val_true = np.concatenate([y for x, y in val_ds], axis=0).flatten()
    val_predictions = model.predict(val_ds, verbose=1).flatten()

    thresholds = np.arange(0.05, 0.95, 0.01)
    f1_scores = [
        f1_score(y_val_true, (val_predictions > t).astype(int))
        for t in thresholds
    ]
    return float(thresholds[np.argmax(f1_scores)])


def evaluar_modelo(model, test_ds, class_names, threshold):
    test_loss, test_acc, test_auc = model.evaluate(test_ds, verbose=1)
    print(f"Test Loss: {test_loss:.4f}")
    print(f"Test Accuracy: {test_acc * 100:.2f}%")
    print(f"Test AUC: {test_auc:.4f}")

    y_true = np.concatenate([y for x, y in test_ds], axis=0).flatten()
    predictions = model.predict(test_ds, verbose=1).flatten()

    y_pred_05 = (predictions > 0.5).astype(int)
    print("\nReporte con threshold=0.5")
    print(classification_report(y_true, y_pred_05, target_names=class_names))
    graficar_matriz_confusion(
        y_true, y_pred_05, class_names, 0.5, 'matriz_confusion_05.png'
    )

    y_pred_opt = (predictions > threshold).astype(int)
    print(f"\nReporte con threshold óptimo={threshold:.2f}")
    print(classification_report(y_true, y_pred_opt, target_names=class_names))
    graficar_matriz_confusion(
        y_true, y_pred_opt, class_names, threshold, 'matriz_confusion_optima.png'
    )

    reporte_dict = classification_report(
        y_true, y_pred_opt, target_names=class_names, output_dict=True
    )
    pd.DataFrame(reporte_dict).transpose().to_csv('reporte_clasificacion.csv')


def main():
    train_ds, val_ds, test_ds = cargar_datasets()
    class_names = train_ds.class_names
    verificar_orden_clases(class_names)

    class_weight_dict = calcular_class_weights(train_ds)
    train_ds, val_ds, test_ds = preparar_pipeline(train_ds, val_ds, test_ds)

    model, base_model = construir_modelo()
    compilar_modelo(model, learning_rate=1e-3)

    history_fase1 = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=EPOCHS_FASE1,
        callbacks=crear_callbacks('best_ai_vs_real_model_fase1.keras'),
        class_weight=class_weight_dict
    )

    descongelar_ultimas_capas(base_model, n_capas=20)
    compilar_modelo(model, learning_rate=1e-5)

    history_fase2 = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=EPOCHS_FASE2,
        callbacks=crear_callbacks('best_ai_vs_real_model_fase2.keras'),
        class_weight=class_weight_dict
    )

    graficar_historial(history_fase1, history_fase2)

    optimal_threshold = calcular_umbral_optimo(model, val_ds)
    with open('umbral_optimo.json', 'w') as f:
        json.dump({'umbral_optimo': optimal_threshold}, f, indent=2)

    evaluar_modelo(model, test_ds, class_names, optimal_threshold)

    model.save('modelo_ai_vs_real_v2.keras')


if __name__ == '__main__':
    main()