#!/bin/bash
# Script para clonar y configurar el repositorio en SageMaker
# Ejecutar en: SageMaker Studio Terminal o Notebook Instance Terminal

echo "======================================================================"
echo "CLONANDO REPOSITORIO EN SAGEMAKER"
echo "======================================================================"

# Paso 1: Navegar al directorio home
cd /home/sagemaker-user  # Para SageMaker Studio
# cd SageMaker            # Descomentar si usas Notebook Instance

echo ""
echo "📍 Directorio actual: $(pwd)"
echo ""

# Paso 2: Clonar el repositorio
echo "📥 Clonando repositorio..."
git clone https://github.com/lbetancourth-dev-blossom/safe_txns_sim_endpoint.git

# Paso 3: Entrar al directorio
cd safe_txns_sim_endpoint

# Paso 4: Cambiar a rama dev
echo ""
echo "🔀 Cambiando a rama dev..."
git checkout dev

# Paso 5: Hacer pull
echo ""
echo "🔄 Sincronizando con origin/dev..."
git pull origin dev

# Paso 6: Configurar git user (opcional pero recomendado)
echo ""
echo "⚙️  Configurando git user..."
git config user.name "SageMaker User"
git config user.email "sagemaker@blossom.com"

# Paso 7: Verificar estado
echo ""
echo "✅ Estado del repositorio:"
git status
echo ""
git log --oneline -3

echo ""
echo "======================================================================"
echo "✅ REPOSITORIO LISTO!"
echo "======================================================================"
echo ""
echo "📂 Ubicación: $(pwd)"
echo "🌿 Rama: $(git branch --show-current)"
echo ""
echo "Archivos principales:"
ls -lh *.md *.ipynb 2>/dev/null
echo ""
echo "Para abrir el notebook:"
echo "  safe-txn-enpoint.ipynb"
echo ""
