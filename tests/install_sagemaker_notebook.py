# Ejecuta esta celda en tu notebook Jupyter para instalar SageMaker en el kernel correcto

import sys
print(f"Python actual: {sys.executable}")
print(f"Versión: {sys.version}")

# Instalar SageMaker 2.220.0
print("\n📦 Instalando SageMaker 2.220.0...")
import subprocess
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "sagemaker==2.220.0", "-q"],
    capture_output=True,
    text=True
)

if result.returncode == 0:
    print("✓ SageMaker instalado exitosamente")
    print("\n🔄 Ahora reinicia el kernel:")
    print("   Kernel → Restart Kernel")
    print("\nLuego ejecuta:")
    print("   from sagemaker.sklearn.model import SKLearnModel")
else:
    print("❌ Error en instalación:")
    print(result.stderr)
