# Pasos para Clonar el Repositorio en SageMaker

## Opción 1: SageMaker Studio

### 1. Abrir SageMaker Studio
- Ve a AWS Console → SageMaker → Studio
- Abre tu dominio de Studio
- Inicia tu aplicación JupyterLab

### 2. Abrir Terminal
- En JupyterLab, ve a: **File → New → Terminal**
- O usa el ícono de terminal en el launcher

### 3. Clonar el Repositorio
```bash
cd /home/sagemaker-user
git clone https://github.com/lbetancourth-dev-blossom/safe_txns_sim_endpoint.git
cd safe_txns_sim_endpoint
```

### 4. Cambiar a la Rama de Desarrollo
```bash
git checkout dev
git pull origin dev
```

### 5. Verificar el Contenido
```bash
ls -la
cat README.md
```

---

## Opción 2: SageMaker Notebook Instance

### 1. Crear o Acceder al Notebook Instance
- Ve a AWS Console → SageMaker → Notebook instances
- Si no existe, crea uno:
  - **Name:** safe-txns-notebook
  - **Instance type:** ml.t3.medium (o ml.t3.large)
  - **IAM role:** SageMaker-ExecutionRole-20250529T153554
- Abre JupyterLab o Jupyter

### 2. Abrir Terminal
- En JupyterLab: **File → New → Terminal**
- En Jupyter: **New → Terminal**

### 3. Clonar el Repositorio
```bash
cd SageMaker
git clone https://github.com/lbetancourth-dev-blossom/safe_txns_sim_endpoint.git
cd safe_txns_sim_endpoint
```

### 4. Cambiar a la Rama de Desarrollo
```bash
git checkout dev
git pull origin dev
```

---

## Opción 3: Con Credenciales SSH (Recomendado para Desarrollo)

### 1. Configurar SSH Key en SageMaker

```bash
# Generar SSH key (si no tienes una)
ssh-keygen -t ed25519 -C "tu-email@blossom.com"

# Copiar la clave pública
cat ~/.ssh/id_ed25519.pub
```

### 2. Agregar SSH Key a GitHub
- Ve a GitHub → Settings → SSH and GPG keys
- Click "New SSH key"
- Pega la clave pública

### 3. Clonar con SSH
```bash
cd /home/sagemaker-user  # o cd SageMaker para notebook instance
git clone git@github.com:lbetancourth-dev-blossom/safe_txns_sim_endpoint.git
cd safe_txns_sim_endpoint
git checkout dev
```

---

## Configuración Post-Clonado

### 1. Configurar Git User
```bash
git config --global user.name "Tu Nombre"
git config --global user.email "tu-email@blossom.com"
```

### 2. Instalar Dependencias Python
```bash
# Instalar dependencias necesarias
pip install boto3 sagemaker pandas numpy scikit-learn joblib

# Para testing
pip install pytest
```

### 3. Configurar AWS Profile (si es necesario)
```bash
# Configurar credenciales AWS
aws configure --profile blossom-dev
# AWS Access Key ID: [tu-key]
# AWS Secret Access Key: [tu-secret]
# Default region name: us-east-1
# Default output format: json
```

### 4. Verificar Acceso a S3
```bash
export AWS_PROFILE=blossom-dev
aws s3 ls s3://blossom-analytics-safe-dev-nv/safe_txns/
```

---

## Estructura del Proyecto Clonado

```
safe_txns_sim_endpoint/
├── README.md
├── safe-txn-enpoint.ipynb          # ⭐ Notebook principal
├── endpoint/
│   ├── inference_rules.py          # Script de inferencia
│   ├── similarity_matcher.py       # ⭐ Similarity matching
│   ├── schema_validator.py         # ⭐ Validación
│   └── statistical_rules.py        # Reglas estadísticas
├── test/
│   ├── test_e2e_with_s3.py        # Tests E2E
│   └── ...
├── docs/
│   ├── SIMILARITY_INTEGRATION.md   # ⭐ Documentación
│   └── ...
└── data/
    └── transactions_test.csv       # Datos de prueba
```

---

## Trabajar con el Notebook Principal

### 1. Abrir el Notebook
```bash
# En JupyterLab, navega a:
safe_txns_sim_endpoint/safe-txn-enpoint.ipynb
```

### 2. Seleccionar Kernel
- Python 3 (Data Science) - recomendado
- O conda_python3

### 3. Ejecutar Celdas
- El notebook tiene 23 celdas
- **NO ejecutar** las celdas de "Step 1" y "Step 2" (preparación de model.tar.gz)
- El modelo ya está en S3: `s3://blossom-analytics-safe-dev-nv/output/kmeans-similarity-endpoint/model.tar.gz`

---

## Comandos Útiles

### Ver Status del Endpoint
```bash
aws sagemaker describe-endpoint --endpoint-name safe-txn-similarity-endpoint
```

### Ver Logs del Endpoint
```bash
aws logs tail /aws/sagemaker/Endpoints/safe-txn-similarity-endpoint --follow
```

### Listar Modelos en S3
```bash
aws s3 ls s3://blossom-analytics-safe-dev-nv/output/kmeans-similarity-endpoint/
```

### Sincronizar Cambios desde GitHub
```bash
git pull origin dev
```

### Crear Nueva Rama para Desarrollo
```bash
git checkout -b feature/mi-nueva-feature
# Hacer cambios
git add .
git commit -m "Descripción de cambios"
git push origin feature/mi-nueva-feature
```

---

## Troubleshooting

### Error: "Permission denied (publickey)"
```bash
# Verifica que la SSH key esté configurada
ssh -T git@github.com
```

### Error: "fatal: could not read Username"
```bash
# Usa SSH en lugar de HTTPS
git remote set-url origin git@github.com:lbetancourth-dev-blossom/safe_txns_sim_endpoint.git
```

### Error: "No module named 'sagemaker'"
```bash
pip install sagemaker
```

---

## Recursos Adicionales

- **Repositorio:** https://github.com/lbetancourth-dev-blossom/safe_txns_sim_endpoint
- **Branch principal:** `dev`
- **Endpoint actual:** `safe-txn-similarity-endpoint`
- **Modelo en S3:** `s3://blossom-analytics-safe-dev-nv/output/kmeans-similarity-endpoint/model.tar.gz`

---

**Nota:** Este repositorio contiene el código del endpoint con similarity matching integrado. El endpoint ya está desplegado en SageMaker.
