#!/usr/bin/env bash
#!/usr/bin/env python3
"""
Serviço para execução de comandos do samba-tool.
Suporta Modo Real (chamando o binário `samba-tool`) e Modo Simulação (Mock Mode).
Detecta automaticamente IP e Domain DN do servidor se não forem informados.
Gerencia Operadores da Plataforma e Auditoria via PostgreSQL (sambacore4_db).
"""

import subprocess
import shlex
import re
import secrets
import os
import socket
import hashlib

# Dependência do PostgreSQL
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    import pty
except ImportError:
    pty = None


def detect_server_ip():
    """Descobre automaticamente o IP principal da máquina no servidor."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def detect_domain_dn():
    """Descobre automaticamente o Domain DN do Samba Active Directory."""
    try:
        cmd = ["samba-tool", "domain", "info", "127.0.0.1"]
        res = subprocess.run(cmd, capture_output=True, text=True)

        for line in res.stdout.splitlines():
            if "Domain" in line and ":" in line:
                domain_name = line.split(":")[1].strip()
                if "." in domain_name:
                    parts = domain_name.split(".")
                    return ",".join([f"DC={p}" for p in parts])
    except Exception:
        pass

    try:
        if os.path.exists("/etc/samba/smb.conf"):
            with open("/etc/samba/smb.conf", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "realm" in line.lower() and "=" in line:
                        realm = line.split("=")[1].strip().lower()
                        parts = realm.split(".")
                        return ",".join([f"DC={p}" for p in parts])
    except Exception:
        pass

    return "DC=academico,DC=local"


class SambaService:
    def __init__(self, mock_mode=False, domain_dn=None, server_ip=None, admin_password=None):
        self.mock_mode = mock_mode
        self.server_ip = server_ip or detect_server_ip()
        self.domain_dn = domain_dn or detect_domain_dn()
        self.admin_password = admin_password or os.environ.get("SAMBA_ADMIN_PASS", "")
        self._active_tokens = set()

        # Configurações de Conexão com o PostgreSQL
        self.db_config = {
            "host": os.environ.get("DB_HOST", "localhost"),
            "database": os.environ.get("DB_NAME", "sambacore4_db"),
            "user": os.environ.get("DB_USER", "sambacore"),
            "password": os.environ.get("DB_PASS", "dominus7even"),
            "port": int(os.environ.get("DB_PORT", 5432))
        }

        # Inicializa tabelas e admin padrão no PostgreSQL
        self._init_postgres_db()

        # Grupos de Segurança do Active Directory (Mock Inicial)
        self._mock_groups = [
            {"name": "Domain Admins", "description": "Administradores do Domínio", "members": ["administrator"]},
            {"name": "Professores_Grp", "description": "Grupo do Corpo Docente", "members": ["prof.roberto"]},
            {"name": "Financeiro_Grp", "description": "Acesso a Pastas do Financeiro", "members": ["ana.financeiro"]},
            {"name": "TI_Suporte", "description": "Equipe de Suporte e TI", "members": ["suporte"]}
        ]

        # Estado inicial das OUs
        self._mock_ous = [
            {"dn": f"OU=TI,{self.domain_dn}", "name": "TI", "description": "Departamento de Tecnologia"},
            {"dn": f"OU=Laboratorios,{self.domain_dn}", "name": "Laboratórios", "description": "Salas de Aula e Labs"},
            {"dn": f"OU=Financeiro,{self.domain_dn}", "name": "Financeiro", "description": "Departamento Financeiro"},
            {"dn": f"OU=Professores,{self.domain_dn}", "name": "Professores", "description": "Corpo Docente"}
        ]
        
        # Usuários AD
        self._mock_users = [
            {
                "username": "administrator",
                "cn": "Administrator",
                "ou": self.domain_dn,
                "email": "admin@academico.local",
                "enabled": True,
                "system": True,
                "created_at": "2026-08-01 10:00:00"
            },
            {
                "username": "krbtgt",
                "cn": "krbtgt",
                "ou": self.domain_dn,
                "email": "",
                "enabled": False,
                "system": True,
                "created_at": "2026-08-01 10:00:00"
            },
            {
                "username": "prof.roberto",
                "cn": "Prof. Roberto Silva",
                "ou": f"OU=Professores,{self.domain_dn}",
                "email": "roberto@academico.local",
                "enabled": True,
                "system": False,
                "created_at": "2026-08-10 14:30:00"
            },
            {
                "username": "ana.financeiro",
                "cn": "Ana Souza",
                "ou": f"OU=Financeiro,{self.domain_dn}",
                "email": "ana@academico.local",
                "enabled": True,
                "system": False,
                "created_at": "2026-08-15 09:15:00"
            }
        ]

        # Computadores / Desktops AD
        self._mock_computers = [
            {
                "name": "LAB-01-PC01",
                "cn": "LAB-01-PC01$",
                "ou": f"OU=Laboratorios,{self.domain_dn}",
                "os": "Windows 11 Pro",
                "ip": "10.0.10.101"
            },
            {
                "name": "LAB-01-PC02",
                "cn": "LAB-01-PC02$",
                "ou": f"OU=Laboratorios,{self.domain_dn}",
                "os": "Windows 11 Pro",
                "ip": "10.0.10.102"
            },
            {
                "name": "DESKTOP-FIN01",
                "cn": "DESKTOP-FIN01$",
                "ou": f"OU=Financeiro,{self.domain_dn}",
                "os": "Windows 10 Pro",
                "ip": "10.0.10.50"
            },
            {
                "name": "SERVER-TI-01",
                "cn": "SERVER-TI-01$",
                "ou": f"OU=TI,{self.domain_dn}",
                "os": "Ubuntu Server 24.04",
                "ip": self.server_ip
            }
        ]

        # GPOs (Group Policy Objects)
        self._mock_gpos = [
            {
                "guid": "{31B2F340-016D-11D2-945F-00C04FB984F9}",
                "name": "Default Domain Policy",
                "status": "Enabled",
                "version": "1.0",
                "links": [self.domain_dn]
            },
            {
                "guid": "{A12B3C4D-5E6F-7A8B-9C0D-1E2F3A4B5C6D}",
                "name": "Politica_Senhas_Fortes_TI",
                "status": "Enabled",
                "version": "2.1",
                "links": [f"OU=TI,{self.domain_dn}", f"OU=Professores,{self.domain_dn}"]
            },
            {
                "guid": "{B23C4D5E-6F7A-8B9C-0D1E-2F3A4B5C6D7E}",
                "name": "Politica_Bloqueio_Laboratorios",
                "status": "Enabled",
                "version": "1.4",
                "links": [f"OU=Laboratorios,{self.domain_dn}"]
            },
            {
                "guid": "{C34D5E6F-7A8B-9C0D-1E2F-3A4B5C6D7E8F}",
                "name": "Politica_Auditoria_Financeira",
                "status": "Enabled",
                "version": "1.0",
                "links": [f"OU=Financeiro,{self.domain_dn}"]
            }
        ]

    def set_mock_mode(self, enabled: bool):
        self.mock_mode = enabled

    # --- CONEXÃO E INICIALIZAÇÃO DO BANCO POSTGRESQL ---

    def _get_db_connection(self):
        """Abre conexão com a base de dados PostgreSQL."""
        return psycopg2.connect(**self.db_config)

    def _hash_password(self, password: str) -> str:
        """Gera um hash SHA256 para senhas dos operadores."""
        return hashlib.sha256(password.encode('utf-8')).hexdigest()

    def _init_postgres_db(self):
        """Cria as tabelas de operadores e audit_logs no PostgreSQL caso não existam."""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()

            # 1. Tabela de Operadores
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS operadores (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    full_name VARCHAR(100),
                    role VARCHAR(20) DEFAULT 'admin',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP WITH TIME ZONE
                );
            """)

            # 2. Tabela de Logs de Auditoria
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    operator_username VARCHAR(50) NOT NULL,
                    action VARCHAR(100) NOT NULL,
                    target VARCHAR(100),
                    details JSONB,
                    ip_address VARCHAR(45),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 3. Garante que exista ao menos o operador admin inicial
            cursor.execute("SELECT COUNT(*) FROM operadores;")
            if cursor.fetchone()[0] == 0:
                admin_hash = self._hash_password("admin123")
                cursor.execute("""
                    INSERT INTO operadores (username, password_hash, full_name, role)
                    VALUES (%s, %s, %s, %s);
                """, ("admin_master", admin_hash, "Administrador Principal", "admin"))

            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"⚠️ Erro ao inicializar tabelas PostgreSQL no SambaService: {e}")

    # --- GERENCIAMENTO DE OPERADORES (PERSISTENTE VIA POSTGRESQL) ---

    def list_platform_users(self):
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT id, username, full_name, role, created_at FROM operadores ORDER BY id ASC;")
            rows = cursor.fetchall()
            
            users_list = [
                {
                    "id": row["id"],
                    "username": row["username"],
                    "full_name": row["full_name"],
                    "role": row["role"],
                    "system": row["username"] == "admin_master",
                    "created_at": str(row["created_at"]) if row.get("created_at") else None
                }
                for row in rows
            ]
            cursor.close()
            conn.close()
            return True, users_list
        except Exception as e:
            return False, f"Erro ao consultar operadores no PostgreSQL: {str(e)}"

    def register_platform_user(self, username, password, full_name=None, role="admin"):
        username = username.strip().lower()
        if not username or not password:
            return False, "Usuário e senha são obrigatórios para o cadastro."

        full_name = full_name.strip() if full_name else username.capitalize()
        pwd_hash = self._hash_password(password)

        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO operadores (username, password_hash, full_name, role)
                VALUES (%s, %s, %s, %s);
            """, (username, pwd_hash, full_name, role))
            
            conn.commit()
            cursor.close()
            conn.close()

            return True, f"Novo operador '{username}' cadastrado no PostgreSQL com sucesso!"
        except psycopg2.IntegrityError:
            return False, f"O operador '{username}' já possui acesso à plataforma."
        except Exception as e:
            return False, f"Erro ao salvar operador no PostgreSQL: {str(e)}"

    def update_platform_user_password(self, username, new_password):
        username = username.strip().lower()
        if not new_password or len(new_password) < 4:
            return False, "A nova senha deve ter no mínimo 4 caracteres."

        pwd_hash = self._hash_password(new_password)

        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("UPDATE operadores SET password_hash = %s WHERE username = %s;", (pwd_hash, username))
            rows_updated = cursor.rowcount
            conn.commit()
            cursor.close()
            conn.close()

            if rows_updated == 0:
                return False, f"Operador '{username}' não encontrado."

            return True, f"Senha do operador '{username}' atualizada com sucesso no PostgreSQL!"
        except Exception as e:
            return False, f"Erro ao atualizar senha no PostgreSQL: {str(e)}"

    def delete_platform_user(self, username):
        username = username.strip().lower()

        if username == "admin_master":
            return False, "Não é permitido excluir o operador administrador principal do sistema."

        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()

            cursor.execute("DELETE FROM operadores WHERE username = %s;", (username,))
            rows_deleted = cursor.rowcount
            conn.commit()
            cursor.close()
            conn.close()

            if rows_deleted > 0:
                return True, f"Acesso do operador '{username}' removido do PostgreSQL com sucesso."
            return False, f"Operador '{username}' não encontrado."
        except Exception as e:
            return False, f"Erro ao remover operador do PostgreSQL: {str(e)}"

    def is_user_in_group(self, username, group_name="Domain Admins"):
        username = username.strip().lower()
        group_name = group_name.strip()

        if self.mock_mode:
            target_grp = next((g for g in self._mock_groups if g["name"].lower() == group_name.lower()), None)
            if target_grp:
                return any(m.lower() == username for m in target_grp["members"]) or username == "administrator"
            return False

        success, output, _ = self._run_cmd(["user", "getgroups", username])
        if not success:
            return False

        user_groups = [line.strip().lower() for line in output.splitlines() if line.strip()]
        return group_name.lower() in user_groups

    def authenticate_user(self, username, password, required_group="Domain Admins"):
        username = username.strip().lower()
        pwd_hash = self._hash_password(password)

        # 1. Tenta autenticar via PostgreSQL (Operadores de Plataforma)
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM operadores WHERE username = %s;", (username,))
            user = cursor.fetchone()

            if user:
                if user["password_hash"] == pwd_hash:
                    cursor.execute("UPDATE operadores SET last_login = NOW() WHERE username = %s;", (username,))
                    conn.commit()
                    cursor.close()
                    conn.close()

                    token = "pg_token_" + secrets.token_hex(16)
                    self._active_tokens.add(token)
                    return True, token, f"Bem-vindo(a), {user['full_name']}!", "[POSTGRESQL] Auth interna OK"
                else:
                    cursor.close()
                    conn.close()
                    return False, None, "Senha incorreta para a conta da plataforma.", "[POSTGRESQL] Senha inválida"
            cursor.close()
            conn.close()
        except Exception:
            pass

        # 2. Modo Simulação (Mock)
        if self.mock_mode:
            user_exists = any(u["username"].lower() == username for u in self._mock_users)
            if not user_exists:
                return False, None, f"Usuário '{username}' não encontrado no banco ou AD.", "[MOCK] Auth falhou"

            if not self.is_user_in_group(username, required_group):
                return False, None, f"Acesso Negado: O usuário '{username}' não pertence ao grupo '{required_group}'.", "[MOCK] Sem permissão"

            token = "ad_token_" + secrets.token_hex(16)
            self._active_tokens.add(token)
            return True, token, f"Bem-vindo(a), {username}! (Autenticado via AD)", "[MOCK] Auth OK"

        # 3. Modo Real (samba-tool)
        cmd = ["sudo", "samba-tool", "user", "checkpassword", username]
        try:
            res = subprocess.run(cmd, input=f"{password}\n", stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            if res.returncode != 0:
                return False, None, "Usuário ou senha incorretos no Active Directory.", "sudo samba-tool user checkpassword"
        except Exception as e:
            return False, None, f"Erro ao conectar ao servidor AD: {str(e)}", "sudo samba-tool user checkpassword"

        if not self.is_user_in_group(username, required_group):
            return False, None, f"Acesso Negado: Seu usuário não pertence ao grupo '{required_group}'.", "sudo samba-tool user getgroups"

        token = "real_token_" + secrets.token_hex(16)
        self._active_tokens.add(token)
        return True, token, "Bem-vindo(a) ao painel! Autenticado com sucesso via AD.", "Auth AD OK"

    def validate_token(self, token):
        return token in self._active_tokens

    def revoke_token(self, token):
        self._active_tokens.discard(token)

    def _run_cmd(self, args: list, input_data: str = None):
        """Executa um comando samba-tool sem shell=True."""
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd = ["samba-tool"] + args
        else:
            cmd = ["sudo", "samba-tool"] + args

        cmd_str = " ".join([shlex.quote(a) for a in cmd])

        if self.mock_mode:
            return True, f"[MOCK EXECUTION] Comando simulado com sucesso: {cmd_str}", cmd_str

        if input_data and pty and hasattr(os, "openpty"):
            try:
                master, slave = pty.openpty()
                proc = subprocess.Popen(cmd, stdin=slave, stdout=slave, stderr=slave, close_fds=True)
                os.close(slave)

                pass_text = input_data if input_data.endswith("\n") else input_data + "\n"
                os.write(master, pass_text.encode("utf-8"))

                output = b""
                while True:
                    try:
                        data = os.read(master, 1024)
                        if not data:
                            break
                        output += data
                    except OSError:
                        break

                proc.wait(timeout=15)
                os.close(master)
                out_str = output.decode("utf-8", errors="ignore").strip()

                if proc.returncode == 0 or ("created as" in out_str and "GPO" in out_str):
                    clean_out = re.sub(r"Password for \[.*?\]:\s*", "", out_str).strip()
                    return True, clean_out, cmd_str
            except Exception:
                try: os.close(master)
                except Exception: pass

        try:
            res = subprocess.run(
                cmd,
                input=input_data,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15
            )
            if res.returncode == 0:
                return True, res.stdout.strip(), cmd_str
            else:
                raw_err = res.stderr.strip() or res.stdout.strip()
                if "LDAP_INSUFFICIENT_ACCESS_RIGHTS" in raw_err or "LDAP error 50" in raw_err:
                    err_msg = (
                        "Erro de Permissão no Samba AD (LDAP_INSUFFICIENT_ACCESS_RIGHTS - Erro 50):\n"
                        "O comando não possui acesso para criar/modificar objetos.\n\n"
                        "💡 Para corrigir no servidor Samba AD, execute no terminal:\n"
                        "1. sudo samba-tool ntacl sysvolreset"
                    )
                    return False, err_msg, cmd_str
                return False, raw_err, cmd_str
        except FileNotFoundError:
            return False, "Erro: O binário 'samba-tool' não foi encontrado no sistema.", cmd_str
        except Exception as e:
            return False, f"Erro na execução do comando: {str(e)}", cmd_str

    # --- USUÁRIOS AD ---

    def list_users(self):
        cmd_preview = "sudo samba-tool user list"
        if self.mock_mode:
            users_list = [u["username"] for u in self._mock_users]
            return True, users_list, self._mock_users, "[MOCK] " + cmd_preview

        success, output, cmd_str = self._run_cmd(["user", "list"])
        if not success:
            return False, [], [], cmd_str
        
        usernames = [line.strip() for line in output.splitlines() if line.strip()]
        detailed_users = []
        for u in usernames:
            detailed_users.append({
                "username": u,
                "cn": u,
                "ou": self.domain_dn,
                "email": f"{u}@academico.local",
                "enabled": True,
                "system": u.lower() in ["administrator", "krbtgt", "guest"]
            })
        return True, usernames, detailed_users, cmd_str

    def create_user(self, username, password, ou=None, surname=None, given_name=None, mail=None):
        username = username.strip()
        args = ["user", "create", username, password]
        
        if ou and ou.strip():
            args.append(f"--userou={ou.strip()}")
        if surname and surname.strip():
            args.append(f"--surname={surname.strip()}")
        if given_name and given_name.strip():
            args.append(f"--given-name={given_name.strip()}")
        if mail and mail.strip():
            args.append(f"--mail-address={mail.strip()}")

        cmd_preview = "sudo samba-tool " + " ".join([shlex.quote(a) for a in args])

        if self.mock_mode:
            if any(u["username"].lower() == username.lower() for u in self._mock_users):
                return False, f"Usuário '{username}' já existe no domínio.", cmd_preview

            import datetime
            new_user = {
                "username": username,
                "cn": f"{given_name or username} {surname or ''}".strip(),
                "ou": ou if (ou and ou.strip()) else self.domain_dn,
                "email": mail or f"{username}@academico.local",
                "enabled": True,
                "system": False,
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self._mock_users.append(new_user)
            return True, f"Usuário '{username}' criado com sucesso!", cmd_preview

        success, msg, cmd_str = self._run_cmd(args)
        return success, msg, cmd_str

    def set_user_password(self, username, new_password):
        username = username.strip()
        new_password = new_password.strip()
        args = ["user", "setpassword", username, f"--newpassword={new_password}"]
        cmd_preview = f"sudo samba-tool user setpassword {shlex.quote(username)} --newpassword='*****'"

        if self.mock_mode:
            target = next((u for u in self._mock_users if u["username"].lower() == username.lower()), None)
            if not target:
                return False, f"Usuário '{username}' não encontrado.", cmd_preview

            return True, f"Senha do usuário AD '{username}' alterada com sucesso!", cmd_preview

        success, msg, cmd_str = self._run_cmd(args)
        return success, msg, cmd_str

    def delete_user(self, username):
        username = username.strip()
        args = ["user", "delete", username]
        cmd_preview = f"sudo samba-tool user delete {shlex.quote(username)}"

        if self.mock_mode:
            target = next((u for u in self._mock_users if u["username"].lower() == username.lower()), None)
            if not target:
                return False, f"Usuário '{username}' não encontrado.", cmd_preview
            if target.get("system"):
                return False, f"Não é permitido excluir o usuário de sistema '{username}'.", cmd_preview

            self._mock_users = [u for u in self._mock_users if u["username"].lower() != username.lower()]
            return True, f"Usuário '{username}' excluído com sucesso!", cmd_preview

        success, msg, cmd_str = self._run_cmd(args)
        return success, msg, cmd_str

    # --- GERENCIAMENTO DE GRUPOS ---

    def list_groups(self):
        cmd_preview = "sudo samba-tool group list"
        if self.mock_mode:
            return True, self._mock_groups, "[MOCK] " + cmd_preview

        success, output, cmd_str = self._run_cmd(["group", "list"])
        if not success:
            return False, [], cmd_str

        groups = []
        for line in output.splitlines():
            grp_name = line.strip()
            if grp_name:
                groups.append({
                    "name": grp_name,
                    "description": f"Grupo de Segurança ({grp_name})",
                    "members": []
                })
        return True, groups, cmd_str

    def create_group(self, group_name, description=""):
        group_name = group_name.strip()
        args = ["group", "add", group_name]
        cmd_preview = f"sudo samba-tool group add {shlex.quote(group_name)}"

        if self.mock_mode:
            if any(g["name"].lower() == group_name.lower() for g in self._mock_groups):
                return False, f"O grupo '{group_name}' já existe.", cmd_preview

            new_grp = {
                "name": group_name,
                "description": description or f"Grupo {group_name}",
                "members": []
            }
            self._mock_groups.append(new_grp)
            return True, f"Grupo '{group_name}' criado com sucesso!", cmd_preview

        success, msg, cmd_str = self._run_cmd(args)
        return success, msg, cmd_str

    def delete_group(self, group_name):
        group_name = group_name.strip()
        args = ["group", "delete", group_name]
        cmd_preview = f"sudo samba-tool group delete {shlex.quote(group_name)}"

        if self.mock_mode:
            target = next((g for g in self._mock_groups if g["name"].lower() == group_name.lower()), None)
            if not target:
                return False, f"Grupo '{group_name}' não encontrado.", cmd_preview

            self._mock_groups = [g for g in self._mock_groups if g["name"].lower() != group_name.lower()]
            return True, f"Grupo '{group_name}' excluído com sucesso!", cmd_preview

        success, msg, cmd_str = self._run_cmd(args)
        return success, msg, cmd_str

    def add_group_member(self, group_name, username):
        group_name = group_name.strip()
        username = username.strip()
        args = ["group", "addmembers", group_name, username]
        cmd_preview = f"sudo samba-tool group addmembers {shlex.quote(group_name)} {shlex.quote(username)}"

        if self.mock_mode:
            target = next((g for g in self._mock_groups if g["name"].lower() == group_name.lower()), None)
            if not target:
                return False, f"Grupo '{group_name}' não encontrado.", cmd_preview

            if username not in target["members"]:
                target["members"].append(username)

            return True, f"Usuário '{username}' adicionado ao grupo '{group_name}' com sucesso!", cmd_preview

        success, msg, cmd_str = self._run_cmd(args)
        return success, msg, cmd_str

    def remove_group_member(self, group_name, username):
        group_name = group_name.strip()
        username = username.strip()
        args = ["group", "removemembers", group_name, username]
        cmd_preview = f"sudo samba-tool group removemembers {shlex.quote(group_name)} {shlex.quote(username)}"

        if self.mock_mode:
            target = next((g for g in self._mock_groups if g["name"].lower() == group_name.lower()), None)
            if target and username in target["members"]:
                target["members"].remove(username)

            return True, f"Usuário '{username}' removido do grupo '{group_name}' com sucesso!", cmd_preview

        success, msg, cmd_str = self._run_cmd(args)
        return success, msg, cmd_str

    # --- COMPUTADORES / DESKTOPS ---

    def list_computers(self):
        cmd_preview = "sudo samba-tool computer list"
        if self.mock_mode:
            return True, self._mock_computers, "[MOCK] " + cmd_preview

        success, output, cmd_str = self._run_cmd(["computer", "list"])
        if not success:
            return False, [], cmd_str

        computers = []
        for line in output.splitlines():
            line = line.strip()
            if line:
                clean_name = line.rstrip("$")
                computers.append({
                    "name": clean_name,
                    "cn": f"{clean_name}$",
                    "ou": self.domain_dn,
                    "os": "Windows / Linux AD Client",
                    "ip": "DHCP / Dinâmico"
                })
        return True, computers, cmd_str

    def create_computer(self, name, ou=None, ip=None, os_name=None):
        name = name.strip()
        args = ["computer", "create", name]
        if ou and ou.strip():
            args.append(f"--computerou={ou.strip()}")

        cmd_preview = "sudo samba-tool " + " ".join([shlex.quote(a) for a in args])

        if self.mock_mode:
            if any(c["name"].lower() == name.lower() for c in self._mock_computers):
                return False, f"Computador '{name}' já está cadastrado no domínio.", cmd_preview

            new_computer = {
                "name": name,
                "cn": f"{name}$",
                "ou": ou if (ou and ou.strip()) else self.domain_dn,
                "os": os_name or "Windows 11 Pro",
                "ip": ip or "10.0.10.X"
            }
            self._mock_computers.append(new_computer)
            return True, f"Computador/Desktop '{name}' adicionado ao domínio com sucesso!", cmd_preview

        success, msg, cmd_str = self._run_cmd(args)
        return success, msg, cmd_str

    def delete_computer(self, name):
        name = name.strip().rstrip("$")
        args = ["computer", "delete", name]
        cmd_preview = f"sudo samba-tool computer delete {shlex.quote(name)}"

        if self.mock_mode:
            target = next((c for c in self._mock_computers if c["name"].lower() == name.lower()), None)
            if not target:
                return False, f"Computador '{name}' não encontrado no domínio.", cmd_preview

            self._mock_computers = [c for c in self._mock_computers if c["name"].lower() != name.lower()]
            return True, f"Computador '{name}' excluído com sucesso do Active Directory!", cmd_preview

        success, msg, cmd_str = self._run_cmd(args)
        return success, msg, cmd_str

    # --- UNIDADES ORGANIZACIONAIS (OUs) ---

    def list_ous(self):
        cmd_preview = "sudo samba-tool ou list"
        if self.mock_mode:
            return True, self._mock_ous, "[MOCK] " + cmd_preview

        success, output, cmd_str = self._run_cmd(["ou", "list"])
        if not success:
            return False, [], cmd_str

        ous = []
        for line in output.splitlines():
            line = line.strip()
            if line:
                match = re.search(r"OU=([^,]+)", line)
                name = match.group(1) if match else line
                ous.append({
                    "dn": line,
                    "name": name,
                    "description": f"Unidade Organizacional {name}"
                })
        return True, ous, cmd_str

    def create_ou(self, ou_name, parent_dn=None):
        ou_name = ou_name.strip()
        if parent_dn and parent_dn.strip():
            ou_dn = f"OU={ou_name},{parent_dn.strip()}"
        else:
            ou_dn = f"OU={ou_name},{self.domain_dn}"

        args = ["ou", "create", ou_dn]
        cmd_preview = f"sudo samba-tool ou create {shlex.quote(ou_dn)}"

        if self.mock_mode:
            if any(o["dn"].lower() == ou_dn.lower() for o in self._mock_ous):
                return False, f"Unidade Organizacional '{ou_dn}' já existe.", cmd_preview

            new_ou = {
                "dn": ou_dn,
                "name": ou_name,
                "description": f"Unidade Organizacional {ou_name}"
            }
            self._mock_ous.append(new_ou)
            return True, f"Unidade Organizacional '{ou_dn}' criada com sucesso!", cmd_preview

        success, msg, cmd_str = self._run_cmd(args)
        return success, msg, cmd_str

    def delete_ou(self, ou_dn):
        ou_dn = ou_dn.strip()
        args = ["ou", "delete", ou_dn]
        cmd_preview = f"sudo samba-tool ou delete {shlex.quote(ou_dn)}"

        if self.mock_mode:
            target = next((o for o in self._mock_ous if o["dn"].lower() == ou_dn.lower()), None)
            if not target:
                return False, f"Unidade Organizacional '{ou_dn}' não encontrada.", cmd_preview

            self._mock_users = [u for u in self._mock_users if u["ou"].lower() != ou_dn.lower()]
            self._mock_computers = [c for c in self._mock_computers if c["ou"].lower() != ou_dn.lower()]
            self._mock_ous = [o for o in self._mock_ous if o["dn"].lower() != ou_dn.lower()]
            return True, f"Unidade Organizacional '{ou_dn}' e seus objetos foram excluídos!", cmd_preview

        success, msg, cmd_str = self._run_cmd(args)
        return success, msg, cmd_str

    # --- OBJETOS DENTRO DE UMA OU ---

    def list_ou_objects(self, ou_dn):
        ou_dn = ou_dn.strip()
        cmd_preview = f"sudo samba-tool ou listobjects {shlex.quote(ou_dn)}"

        if self.mock_mode:
            users_in_ou = [
                {
                    "name": u["username"],
                    "type": "user",
                    "dn": f"CN={u['username']},{ou_dn}",
                    "details": u["email"] or "Usuário de Domínio"
                }
                for u in self._mock_users if u["ou"].lower() == ou_dn.lower()
            ]

            computers_in_ou = [
                {
                    "name": c["name"],
                    "type": "computer",
                    "dn": f"CN={c['name']},{ou_dn}",
                    "details": f"Computador / Desktop ({c['os']})"
                }
                for c in self._mock_computers if c["ou"].lower() == ou_dn.lower()
            ]

            sub_ous = [
                {
                    "name": o["name"],
                    "type": "organizationalUnit",
                    "dn": o["dn"],
                    "details": "Sub-Unidade Organizacional"
                }
                for o in self._mock_ous if o["dn"].lower().endswith("," + ou_dn.lower()) and o["dn"].lower() != ou_dn.lower()
            ]
            
            objects = users_in_ou + computers_in_ou + sub_ous
            return True, objects, "[MOCK] " + cmd_preview

        success, output, cmd_str = self._run_cmd(["ou", "listobjects", ou_dn])
        if not success:
            return False, [], cmd_str

        objects = []
        for line in output.splitlines():
            line = line.strip()
            if line:
                if "$" in line or "computer" in line.lower():
                    obj_type = "computer"
                elif "CN=" in line.upper():
                    obj_type = "user"
                else:
                    obj_type = "organizationalUnit"

                name_match = re.search(r"(?:CN|OU)=([^,]+)", line, re.IGNORECASE)
                name = name_match.group(1) if name_match else line
                name = name.rstrip("$")

                objects.append({
                    "name": name,
                    "type": obj_type,
                    "dn": line,
                    "details": f"Objeto Active Directory ({obj_type})"
                })
        return True, objects, cmd_str

    def delete_object_in_ou(self, object_dn, object_type="user"):
        object_dn = object_dn.strip()
        
        if object_type == "computer" or "$" in object_dn:
            match = re.search(r"CN=([^,]+)", object_dn, re.IGNORECASE)
            comp_name = match.group(1) if match else object_dn
            return self.delete_computer(comp_name)
        elif object_type == "user" or "CN=" in object_dn.upper():
            match = re.search(r"CN=([^,]+)", object_dn, re.IGNORECASE)
            username = match.group(1) if match else object_dn
            return self.delete_user(username)
        elif object_type == "organizationalUnit" or "OU=" in object_dn.upper():
            return self.delete_ou(object_dn)
        else:
            return self.delete_ou(object_dn)

    # --- GERENCIAMENTO DE GPOs (GROUP POLICY OBJECTS) ---

    def list_gpos(self):
        cmd_preview = "sudo samba-tool gpo listall"
        if self.mock_mode:
            gpos_by_ou = {}
            for g in self._mock_gpos:
                for link in g["links"]:
                    if link not in gpos_by_ou:
                        gpos_by_ou[link] = []
                    gpos_by_ou[link].append(g)

            return True, self._mock_gpos, gpos_by_ou, "[MOCK] " + cmd_preview

        success, output, cmd_str = self._run_cmd(["gpo", "listall"])
        if not success:
            return False, [], {}, cmd_str

        gpos = []
        current_gpo = None

        for line in output.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue

            parts = line.split(":", 1)
            key = parts[0].strip().lower()
            val = parts[1].strip()

            if key == "gpo":
                if current_gpo and current_gpo.get("name"):
                    gpos.append(current_gpo)
                current_gpo = {
                    "guid": val,
                    "name": "",
                    "status": "Enabled",
                    "version": "1.0",
                    "links": []
                }
            elif key == "display name" and current_gpo is not None:
                current_gpo["name"] = val
            elif key == "path" and current_gpo is not None:
                current_gpo["path"] = val
            elif key == "dn" and current_gpo is not None:
                current_gpo["dn"] = val

        if current_gpo and current_gpo.get("name"):
            gpos.append(current_gpo)

        return True, gpos, {}, cmd_str

    def create_gpo(self, display_name, admin_user=None, admin_password=None):
        display_name = display_name.strip()
        user_param = admin_user.strip() if admin_user else "Administrator"
        pass_param = admin_password if admin_password is not None and admin_password != "" else self.admin_password

        cmd_preview = f"sudo samba-tool gpo create {shlex.quote(display_name)}"

        if self.mock_mode:
            if any(g["name"].lower() == display_name.lower() for g in self._mock_gpos):
                return False, f"A GPO '{display_name}' já existe no domínio.", cmd_preview

            new_guid = "{" + secrets.token_hex(4).upper() + "-" + secrets.token_hex(2).upper() + "-" + secrets.token_hex(2).upper() + "-" + secrets.token_hex(2).upper() + "-" + secrets.token_hex(6).upper() + "}"
            new_gpo = {
                "guid": new_guid,
                "name": display_name,
                "status": "Enabled",
                "version": "1.0",
                "links": []
            }
            self._mock_gpos.append(new_gpo)
            return True, f"GPO '{display_name}' criada com sucesso! GUID: {new_guid}", cmd_preview

        # MODO REAL VIA LISTA DE ARGUMENTOS
        cmd = ["samba-tool", "gpo", "create", display_name]
        if pass_param:
            cmd.extend(["-U", user_param, f"--password={pass_param}"])

        if hasattr(os, "geteuid") and os.geteuid() != 0:
            cmd.insert(0, "sudo")

        process = subprocess.run(cmd, capture_output=True, text=True)
        if process.returncode == 0:
            match = re.search(r"\{[A-F0-9-]+\}", process.stdout, re.IGNORECASE)
            guid = match.group(0) if match else ""
            return True, f"GPO '{display_name}' criada com sucesso! {guid}".strip(), cmd_preview
        
        return False, process.stderr or "Erro ao criar GPO no Samba.", cmd_preview

    def delete_gpo(self, gpo_guid, admin_user=None, admin_pass=None):
        """Exclui permanentemente uma GPO do domínio."""
        gpo_guid = gpo_guid.strip()
        cmd_preview = f"sudo samba-tool gpo del {shlex.quote(gpo_guid)}"

        if self.mock_mode:
            target = next((g for g in self._mock_gpos if g["guid"].lower() == gpo_guid.lower() or g["name"].lower() == gpo_guid.lower()), None)
            if not target:
                return False, f"GPO '{gpo_guid}' não encontrada.", cmd_preview

            self._mock_gpos = [g for g in self._mock_gpos if g["guid"].lower() != gpo_guid.lower() and g["name"].lower() != gpo_guid.lower()]
            return True, f"GPO '{target['name']}' excluída com sucesso!", cmd_preview

        # MODO REAL VIA LISTA DE ARGUMENTOS
        cmd = ["samba-tool", "gpo", "del", gpo_guid]
        if admin_user and admin_pass:
            cmd.extend(["-U", admin_user, f"--password={admin_pass}"])

        if hasattr(os, "geteuid") and os.geteuid() != 0:
            cmd.insert(0, "sudo")

        process = subprocess.run(cmd, capture_output=True, text=True)
        if process.returncode == 0:
            return True, f"GPO '{gpo_guid}' excluída com sucesso!", cmd_preview

        return False, process.stderr or "Erro ao excluir GPO no Samba.", cmd_preview

    def link_gpo(self, container_dn, gpo_guid):
        container_dn = container_dn.strip()
        gpo_guid = gpo_guid.strip()

        cmd_preview = f"sudo samba-tool gpo setlink {shlex.quote(container_dn)} {shlex.quote(gpo_guid)}"

        if self.mock_mode:
            target_gpo = next((g for g in self._mock_gpos if g["guid"].lower() == gpo_guid.lower() or g["name"].lower() == gpo_guid.lower()), None)
            if not target_gpo:
                return False, f"GPO '{gpo_guid}' não encontrada.", cmd_preview

            if container_dn not in target_gpo["links"]:
                target_gpo["links"].append(container_dn)

            return True, f"GPO '{target_gpo['name']}' vinculada à OU/Container '{container_dn}' com sucesso!", cmd_preview

        success, msg, cmd_str = self._run_cmd(["gpo", "setlink", container_dn, gpo_guid, "-k", "yes"])
        if not success:
            success, msg, cmd_str = self._run_cmd(["gpo", "setlink", container_dn, gpo_guid, "-P"])
        if not success:
            success, msg, cmd_str = self._run_cmd(["gpo", "setlink", container_dn, gpo_guid])
        return success, msg, cmd_str

    def unlink_gpo(self, container_dn, gpo_guid):
        container_dn = container_dn.strip()
        gpo_guid = gpo_guid.strip()

        cmd_preview = f"sudo samba-tool gpo dellink {shlex.quote(container_dn)} {shlex.quote(gpo_guid)}"

        if self.mock_mode:
            target_gpo = next((g for g in self._mock_gpos if g["guid"].lower() == gpo_guid.lower() or g["name"].lower() == gpo_guid.lower()), None)
            if target_gpo and container_dn in target_gpo["links"]:
                target_gpo["links"].remove(container_dn)

            return True, f"Vínculo da GPO com a OU '{container_dn}' removido com sucesso!", cmd_preview

        success, msg, cmd_str = self._run_cmd(["gpo", "dellink", container_dn, gpo_guid, "-k", "yes"])
        if not success:
            success, msg, cmd_str = self._run_cmd(["gpo", "dellink", container_dn, gpo_guid, "-P"])
        if not success:
            success, msg, cmd_str = self._run_cmd(["gpo", "dellink", container_dn, gpo_guid])
        return success, msg, cmd_str

    def get_system_info(self):
        """Retorna informações detalhadas de hardware e métricas do sistema."""
        import platform
        import shutil

        try:
            import psutil
            has_psutil = True
        except ImportError:
            has_psutil = False

        cpu_model = ""
        if os.path.exists("/proc/cpuinfo"):
            try:
                with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "model name" in line:
                            cpu_model = line.split(":", 1)[1].strip()
                            break
            except Exception:
                pass
        if not cpu_model:
            cpu_model = platform.processor() or platform.machine() or "Processador Genérico x86_64"

        cpu_cores = os.cpu_count() or 1
        cpu_percent = psutil.cpu_percent(interval=None) if has_psutil else 15.0

        if has_psutil:
            try:
                mem = psutil.virtual_memory()
                ram_total_gb = round(mem.total / (1024 ** 3), 2)
                ram_used_gb = round(mem.used / (1024 ** 3), 2)
                ram_free_gb = round(mem.available / (1024 ** 3), 2)
                ram_percent = mem.percent
            except Exception:
                ram_total_gb, ram_used_gb, ram_free_gb, ram_percent = 16.0, 4.2, 11.8, 26.25
        else:
            ram_total_gb, ram_used_gb, ram_free_gb, ram_percent = 16.0, 4.2, 11.8, 26.25

        os_name = ""
        if os.path.exists("/etc/os-release"):
            try:
                os_info = {}
                with open("/etc/os-release", "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "=" in line:
                            k, v = line.strip().split("=", 1)
                            os_info[k] = v.strip('"')
                if "PRETTY_NAME" in os_info:
                    os_name = os_info["PRETTY_NAME"]
            except Exception:
                pass
        if not os_name:
            os_name = f"{platform.system()} {platform.release()}"

        try:
            disk = shutil.disk_usage("/")
            disk_total_gb = round(disk.total / (1024 ** 3), 2)
            disk_used_gb = round(disk.used / (1024 ** 3), 2)
            disk_free_gb = round(disk.free / (1024 ** 3), 2)
            disk_percent = round((disk.used / disk.total) * 100, 1)
        except Exception:
            disk_total_gb, disk_used_gb, disk_free_gb, disk_percent = 100.0, 35.5, 64.5, 35.5

        return {
            "cpu": {
                "model": cpu_model,
                "cores": cpu_cores,
                "usage_percent": cpu_percent
            },
            "ram": {
                "total_gb": ram_total_gb,
                "used_gb": ram_used_gb,
                "free_gb": ram_free_gb,
                "usage_percent": ram_percent
            },
            "os": {
                "name": os_name,
                "architecture": platform.machine(),
                "kernel": platform.release()
            },
            "disk": {
                "total_gb": disk_total_gb,
                "used_gb": disk_used_gb,
                "free_gb": disk_free_gb,
                "usage_percent": disk_percent
            },
            "network": {
                "download_speed": "125.4 Mbps",
                "upload_speed": "48.0 Mbps",
                "latency": "12 ms",
                "interface_status": "Online (1 Gbps Full Duplex)",
                "status": "Conectado"
            }
        }

    # --- HISTÓRICO / LOG DE ÚLTIMOS USUÁRIOS CRIADOS ---

    def get_recent_users(self, limit=20):
        """
        Retorna os últimos 'limit' usuários criados no Samba AD.
        Utiliza o ldbsearch no modo real para consultar o atributo LDAP 'whenCreated'.
        """
        cmd_preview = "ldbsearch -H /var/lib/samba/private/sam.ldb '(&(objectClass=user)(objectCategory=person))' sAMAccountName whenCreated"

        if self.mock_mode:
            sorted_mock = sorted(
                self._mock_users,
                key=lambda u: u.get("created_at", ""),
                reverse=True
            )
            recent_mock = [
                {
                    "username": u["username"],
                    "created_at": u.get("created_at", "N/A"),
                    "ou": u.get("ou", self.domain_dn)
                }
                for u in sorted_mock[:limit]
            ]
            return True, recent_mock, "[MOCK] " + cmd_preview

        try:
            cmd = [
                "sudo", "ldbsearch",
                "-H", "/var/lib/samba/private/sam.ldb",
                "(&(objectClass=user)(objectCategory=person))",
                "sAMAccountName", "whenCreated"
            ]
            
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            
            if process.returncode != 0:
                return False, [], process.stderr or "Erro ao consultar sam.ldb"

            users = []
            entries = process.stdout.split("\n\n")

            for entry in entries:
                if not entry.strip():
                    continue
                
                current_user = {}
                for line in entry.splitlines():
                    if ":" in line:
                        key, val = line.split(":", 1)
                        key = key.strip()
                        val = val.strip()
                        if key == "sAMAccountName":
                            current_user["username"] = val
                        elif key == "whenCreated":
                            if len(val) >= 14:
                                formatted_date = f"{val[0:4]}-{val[4:6]}-{val[6:8]} {val[8:10]}:{val[10:12]}:{val[12:14]}"
                            else:
                                formatted_date = val
                            current_user["created_at"] = formatted_date

                if "username" in current_user:
                    if not current_user["username"].endswith("$"):
                        if "created_at" not in current_user:
                            current_user["created_at"] = "1970-01-01 00:00:00"
                        users.append(current_user)

            sorted_users = sorted(
                users,
                key=lambda u: u.get("created_at", ""),
                reverse=True
            )

            return True, sorted_users[:limit], cmd_preview

        except Exception as e:
            return False, [], str(e)