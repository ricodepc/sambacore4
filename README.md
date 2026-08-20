# 🚀 SambaCore 4

O **SambaCore 4** é uma solução completa de gerenciamento com painel web integrado, backend Python (Flask), banco de dados PostgreSQL e proxy reverso Nginx com suporte a SSL/HTTPS.
[Dashboard SambaCore4](public/dashboard.png)
---

## 🛠️ Requisitos do Sistema

- **Sistema Operacional:** Linux (Debian 11+, Ubuntu 20.04+ ou distribuições derivadas do Debian)
- **Acesso:** Privilégios de **root** ou usuário com suporte a `sudo`
- **Conectividade:** Acesso à internet para download dos pacotes e dependências

---

## 📥 Guia de Instalação Rápida

Siga os passos abaixo para clonar o repositório e rodar o script de instalação automatizada:

### 1. Clonar o Repositório

Abra o terminal do seu servidor e clone o projeto:

# 1. Clona o repositório
git clone https://github.com/ricodepc/sambacore4.git

# 2. Entra na pasta clonada
cd sambacore4

# 3. Dá permissão de execução ao instalador
chmod +x installsmbc4.sh

# 4. Executa o provisionamento como root
sudo ./installsmbc4.sh


OU

```bash
git clone [https://github.com/ricodepc/sambacore4.git](https://github.com/ricodepc/sambacore4.git)
cd sambacore4



SAMBACORE4

/opt/sambacore4/
├── public/              # Interface Web (HTML, CSS, JS, Imagens)
├── venv/                # Ambiente Virtual Python com dependências
├── server.py            # Servidor Principal Backend (Flask)
├── samba_service.py     # Serviço/Módulo auxiliar do Samba
└── installsmbc4.sh      # Script de instalação e provisionamento





