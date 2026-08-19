#!/bin/bash

# ==============================================================================
#  SambaCore 4 - Script de Instalação e Configuração Automática
#  Inclui: Dependências, PostgreSQL, Systemd Service, SSL e Nginx (Porta 8443)
# ==============================================================================

set -e

# Cores para o terminal
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # Sem Cor

echo -e "${BLUE}====================================================${NC}"
echo -e "${GREEN}      Iniciando Instalação do SambaCore 4          ${NC}"
echo -e "${BLUE}====================================================${NC}"

# 1. Verificar se está rodando como Root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Erro: Este script precisa ser executado como root (sudo ./install.sh).${NC}"
  exit 1
fi

INSTALL_DIR="/opt/sambacore4"
DB_NAME="sambacore4_db"
DB_USER="sambacore"
DB_PASS="dominus7even"

# 2. Atualizar Pacotes e Instalar Dependências do Sistema
echo -e "\n${BLUE}[1/6] Instalando dependências do sistema, Nginx e psmisc...${NC}"
apt-get update -y
apt-get install -y python3 python3-pip python3-venv postgresql postgresql-contrib nginx openssl psmisc

# 3. Criar Diretório da Aplicação e Copiar Arquivos da Pasta Atual
echo -e "\n${BLUE}[2/6] Configurando estrutura de arquivos em $INSTALL_DIR...${NC}"
mkdir -p "$INSTALL_DIR"

CURRENT_DIR=$(pwd)
if [ "$CURRENT_DIR" != "$INSTALL_DIR" ] && [ -f "$CURRENT_DIR/server.py" ]; then
    echo -e "${BLUE}Copiando arquivos do projeto para $INSTALL_DIR...${NC}"
    cp -r "$CURRENT_DIR"/* "$INSTALL_DIR/"
fi

# Ajustar porta do server.py para 5000 para nao conflitar com Nginx (8443)
if [ -f "$INSTALL_DIR/server.py" ]; then
    sed -i 's/PORT = 8443/PORT = 5000/g' "$INSTALL_DIR/server.py" 2>/dev/null || true
fi

chmod -R 777 "$INSTALL_DIR"

# 4. Configurar Banco de Dados PostgreSQL
echo -e "\n${BLUE}[3/6] Configurando o PostgreSQL...${NC}"
systemctl start postgresql
systemctl enable postgresql

sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" 2>/dev/null || true

# 5. Configurar Ambiente Virtual Python (venv) e Bibliotecas de IA
echo -e "\n${BLUE}[4/6] Configurando ambiente virtual Python e bibliotecas (incluindo IA)...${NC}"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install flask flask-cors psycopg2-binary psutil scikit-learn pandas numpy

chmod -R 777 "$INSTALL_DIR"

# 6. Criar/Atualizar Serviço no Systemd
echo -e "\n${BLUE}[5/6] Configurando serviço Systemd (sambacore.service)...${NC}"
cat <<EOF > /etc/systemd/system/sambacore.service
[Unit]
Description=Samba Core 4 Web Panel Daemon
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="DB_HOST=localhost"
Environment="DB_NAME=$DB_NAME"
Environment="DB_USER=$DB_USER"
Environment="DB_PASS=$DB_PASS"
Environment="DB_PORT=5432"
ExecStart=$INSTALL_DIR/venv/bin/python3 server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Encerrar processos pendurados na porta 5000 antes de iniciar
fuser -k 5000/tcp 2>/dev/null || true
pkill -9 -f "server.py" 2>/dev/null || true

systemctl daemon-reload
systemctl enable sambacore
systemctl restart sambacore || true

# 7. Liberar portas e Configurar HTTPS na Porta 8443 com Nginx
echo -e "\n${BLUE}[6/6] Removendo conflitos de porta, Gerando SSL e Configurando Nginx...${NC}"

systemctl stop apache2 2>/dev/null || true
systemctl disable apache2 2>/dev/null || true
apt-get purge -y apache2 apache2-utils apache2-bin 2>/dev/null || true
apt-get autoremove -y 2>/dev/null || true

fuser -k 80/tcp 8443/tcp 2>/dev/null || true

SSL_CERT_PATH="/etc/ssl/certs/sambacore.crt"
SSL_KEY_PATH="/etc/ssl/private/sambacore.key"

if [ ! -f "$SSL_CERT_PATH" ]; then
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$SSL_KEY_PATH" \
        -out "$SSL_CERT_PATH" \
        -subj "/CN=sambacore" 2>/dev/null
fi

cat <<EOF > /etc/nginx/sites-available/sambacore
server {
    listen 80;
    server_name _;
    return 301 https://\$host:8443\$request_uri;
}

server {
    listen 8443 ssl;
    server_name _;

    ssl_certificate $SSL_CERT_PATH;
    ssl_certificate_key $SSL_KEY_PATH;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    error_page 497 https://\$host:8443\$request_uri;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -sf /etc/nginx/sites-available/sambacore /etc/nginx/sites-enabled/sambacore
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl restart nginx

echo -e "\n${GREEN}====================================================${NC}"
echo -e "${GREEN}   Instalação Concluída com Sucesso! 🎉             ${NC}"
echo -e "${GREEN}====================================================${NC}"
echo -e "Acesse o painel com HTTPS em: ${BLUE}https://$(hostname -I | awk '{print $1}'):8443${NC}"
echo -e "Usuário Padrão da Plataforma: ${BLUE}admin_master${NC}"
echo -e "Senha Padrão: ${BLUE}admin123${NC}"
echo -e "${GREEN}====================================================${NC}"