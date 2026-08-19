#!/usr/bin/env python3
"""
Servidor Backend para o Samba AD Web Manager.
Servidor em Python 3 integrado ao Nginx Proxy Reverso.
Trata autenticação, operadores da plataforma, usuários AD, OUs, computadores, GPOs, troca de senhas
e Análise Preditiva de Segurança com IA.
"""

import http.server
import socketserver
import json
import os
import urllib.parse
import subprocess
from samba_service import SambaService

# Importação defensiva do módulo de IA para não quebrar a API caso falhe
try:
    from ai_detector import detector as ai_detector
except Exception as e:
    ai_detector = None
    print(f"⚠️ Aviso: Módulo de IA não pôde ser carregado: {e}")

# Definida para 5000 para não conflitar com a porta 8443 do Nginx
PORT = 5000
PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")

# Instanciação dinâmica do serviço Samba
samba_svc = SambaService(mock_mode=False)

class SambaHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def _send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _read_body_json(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body_bytes = self.rfile.read(content_length)
        try:
            return json.loads(body_bytes.decode("utf-8"))
        except Exception:
            return {}

    def _check_auth(self):
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False
        token = auth_header.split("Bearer ", 1)[1].strip()
        return samba_svc.validate_token(token)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        # Remove barra final para padronizar (ex: /api/status/ vira /api/status)
        path = parsed_url.path.rstrip("/") if parsed_url.path != "/" else "/"
        query = urllib.parse.parse_qs(parsed_url.query)

        if path == "/api/status":
            _, users, detailed_users, _ = samba_svc.list_users()
            _, ous, _ = samba_svc.list_ous()
            _, comps, _ = samba_svc.list_computers()
            _, gpos, _, _ = samba_svc.list_gpos()
            sys_info = samba_svc.get_system_info()
            return self._send_json(200, {
                "mock_mode": samba_svc.mock_mode,
                "domain_dn": samba_svc.domain_dn,
                "server_ip": samba_svc.server_ip,
                "user_count": len(detailed_users),
                "ou_count": len(ous),
                "computer_count": len(comps),
                "gpo_count": len(gpos),
                "server_status": "online",
                "system_info": sys_info
            })

        if path == "/api/system-info":
            sys_info = samba_svc.get_system_info()
            return self._send_json(200, {"success": True, "system_info": sys_info})

        if path.startswith("/api/"):
            if not self._check_auth():
                return self._send_json(401, {"success": False, "error": "Não autorizado. Efetue login no sistema."})

        # --- ROTA DE ANÁLISE DE SEGURANÇA VIA IA ---
        if path == "/api/ai/security-analysis":
            if not ai_detector:
                return self._send_json(503, {
                    "success": False, 
                    "error": "O módulo de IA não está carregado no servidor. Verifique as dependências (scikit-learn/pandas)."
                })
            
            try:
                analysis_result = ai_detector.train_and_predict()
                return self._send_json(200, {
                    "success": True,
                    "analysis": analysis_result
                })
            except Exception as e:
                return self._send_json(500, {
                    "success": False, 
                    "error": f"Falha ao executar inferência de IA: {str(e)}"
                })

        if path == "/api/platform-users":
            success, platform_users = samba_svc.list_platform_users()
            return self._send_json(200, {"success": True, "operators": platform_users})

        elif path == "/api/users":
            success, raw_list, detailed_users, cmd_preview = samba_svc.list_users()
            return self._send_json(200 if success else 400, {
                "success": success,
                "users": detailed_users,
                "cmd_preview": cmd_preview
            })

        elif path == "/api/computers":
            success, computers, cmd_preview = samba_svc.list_computers()
            return self._send_json(200 if success else 400, {
                "success": success,
                "computers": computers,
                "cmd_preview": cmd_preview
            })

        elif path == "/api/ous":
            success, ous, cmd_preview = samba_svc.list_ous()
            return self._send_json(200 if success else 400, {
                "success": success,
                "ous": ous,
                "cmd_preview": cmd_preview
            })

        elif path == "/api/gpos":
            success, gpos, gpos_by_ou, cmd_preview = samba_svc.list_gpos()
            return self._send_json(200 if success else 400, {
                "success": success,
                "gpos": gpos,
                "gpos_by_ou": gpos_by_ou,
                "cmd_preview": cmd_preview
            })

        elif path == "/api/ous/objects":
            ou_dn = query.get("dn", [""])[0]
            if not ou_dn:
                return self._send_json(400, {"success": False, "error": "Parâmetro 'dn' é obrigatório."})
            
            success, objects, cmd_preview = samba_svc.list_ou_objects(ou_dn)
            return self._send_json(200 if success else 400, {
                "success": success,
                "objects": objects,
                "cmd_preview": cmd_preview
            })

        return super().do_GET()

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.rstrip("/") if parsed_url.path != "/" else "/"
        data = self._read_body_json()

        # LOGIN (PÚBLICO)
        if path == "/api/login":
            username = data.get("username", "")
            password = data.get("password", "")
            if not username or not password:
                return self._send_json(400, {"success": False, "error": "Informe o usuário e a senha."})

            success, token, msg, cmd_preview = samba_svc.authenticate_user(username, password)
            return self._send_json(200 if success else 401, {
                "success": success,
                "token": token,
                "message": msg if success else None,
                "error": msg if not success else None,
                "cmd_preview": cmd_preview
            })

        # LOGOUT
        elif path == "/api/logout":
            auth_header = self.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.split("Bearer ", 1)[1].strip()
                samba_svc.revoke_token(token)
            return self._send_json(200, {"success": True, "message": "Sessão encerrada com sucesso."})

        # PROTEÇÃO DE DEMAIS ROTAS POST
        if not self._check_auth():
            return self._send_json(401, {"success": False, "error": "Sessão expirada ou não autorizada."})

        # --- ROTAS DE GERENCIAMENTO E SISTEMA ---
        if path == "/api/system/power":
            action = data.get("action", "").lower()
            
            if action in ["reboot", "restart"]:
                try:
                    subprocess.Popen(["sudo", "systemctl", "reboot"])
                    return self._send_json(200, {"success": True, "message": "Comando de reinicialização enviado com sucesso!"})
                except Exception as e:
                    return self._send_json(500, {"success": False, "error": f"Falha ao reiniciar: {str(e)}"})

            elif action in ["shutdown", "poweroff"]:
                try:
                    subprocess.Popen(["sudo", "shutdown", "-h", "now"])
                    return self._send_json(200, {"success": True, "message": "Comando de desligamento enviado com sucesso!"})
                except Exception as e:
                    return self._send_json(500, {"success": False, "error": f"Falha ao desligar: {str(e)}"})

            else:
                return self._send_json(400, {"success": False, "error": f"Ação de energia inválida: '{action}'."})

        elif path in ["/api/system/reboot", "/api/reboot"]:
            try:
                subprocess.Popen(["sudo", "systemctl", "reboot"])
                return self._send_json(200, {"success": True, "message": "Comando de reinicialização enviado com sucesso!"})
            except Exception as e:
                return self._send_json(500, {"success": False, "error": f"Falha ao executar o comando: {str(e)}"})

        elif path in ["/api/system/shutdown", "/api/shutdown"]:
            try:
                subprocess.Popen(["sudo", "shutdown", "-h", "now"])
                return self._send_json(200, {"success": True, "message": "Comando de desligamento enviado com sucesso!"})
            except Exception as e:
                return self._send_json(500, {"success": False, "error": f"Falha ao executar o comando: {str(e)}"})

        elif path == "/api/platform-users":
            username = data.get("username", "")
            password = data.get("password", "")
            full_name = data.get("full_name", "")

            success, msg = samba_svc.register_platform_user(username, password, full_name)
            return self._send_json(200 if success else 400, {
                "success": success,
                "message": msg if success else None,
                "error": msg if not success else None
            })

        elif path == "/api/status/mode":
            enable_mock = data.get("mock_mode", True)
            samba_svc.set_mock_mode(enable_mock)
            return self._send_json(200, {
                "success": True,
                "mock_mode": samba_svc.mock_mode,
                "message": f"Modo alterado para {'Simulação (Mock)' if samba_svc.mock_mode else 'Real (samba-tool)'}."
            })

        elif path == "/api/users":
            username = data.get("username", "")
            password = data.get("password", "")
            ou = data.get("ou", None)
            given_name = data.get("given_name", None)
            surname = data.get("surname", None)
            mail = data.get("mail", None)

            if not username or not password:
                return self._send_json(400, {"success": False, "error": "Usuário e senha são obrigatórios."})

            success, msg, cmd_preview = samba_svc.create_user(
                username=username,
                password=password,
                ou=ou,
                given_name=given_name,
                surname=surname,
                mail=mail
            )
            return self._send_json(200 if success else 400, {
                "success": success,
                "message": msg if success else None,
                "error": msg if not success else None,
                "cmd_preview": cmd_preview
            })

        elif path == "/api/users/setpassword":
            username = data.get("username", "")
            new_password = data.get("new_password", "")

            if not username or not new_password:
                return self._send_json(400, {"success": False, "error": "Usuário e nova senha são obrigatórios."})

            success, msg, cmd_preview = samba_svc.set_user_password(username, new_password)
            return self._send_json(200 if success else 400, {
                "success": success,
                "message": msg if success else None,
                "error": msg if not success else None,
                "cmd_preview": cmd_preview
            })

        elif path == "/api/computers":
            name = data.get("name", "")
            ou = data.get("ou", None)
            ip = data.get("ip", None)
            os_name = data.get("os", None)

            if not name:
                return self._send_json(400, {"success": False, "error": "Nome do computador é obrigatório."})

            success, msg, cmd_preview = samba_svc.create_computer(name, ou, ip, os_name)
            return self._send_json(200 if success else 400, {
                "success": success,
                "message": msg if success else None,
                "error": msg if not success else None,
                "cmd_preview": cmd_preview
            })

        elif path == "/api/ous":
            name = data.get("name", "")
            parent_dn = data.get("parent_dn", None)

            if not name:
                return self._send_json(400, {"success": False, "error": "Nome da OU é obrigatório."})

            success, msg, cmd_preview = samba_svc.create_ou(name, parent_dn)
            return self._send_json(200 if success else 400, {
                "success": success,
                "message": msg if success else None,
                "error": msg if not success else None,
                "cmd_preview": cmd_preview
            })

        elif path == "/api/gpos":
            display_name = data.get("display_name", "")
            admin_user = data.get("admin_user", None)
            admin_pass = data.get("admin_pass", None)

            if not display_name:
                return self._send_json(400, {"success": False, "error": "Nome da GPO é obrigatório."})

            if admin_user and admin_pass:
               cmd = [
                   "sudo",
                   "samba-tool",
                   "gpo",
                   "create",
                   display_name,
                   "-U",
                   admin_user,
                   f"--password={admin_pass}",
               ]
               
               process = subprocess.run(cmd, capture_output=True, text=True)

               if process.returncode == 0:
                   return self._send_json(200, {
                       "success": True,
                       "message": f'GPO "{display_name}" criada com sucesso!',
                       "cmd_preview": f"samba-tool gpo create '{display_name}' -U '{admin_user}' --password='*****'"
                   })
               else:
                   return self._send_json(400, {
                       "success": False,
                       "error": process.stderr or "Erro ao executar samba-tool",
                   })
            else:
                 success, msg, cmd_preview = samba_svc.create_gpo(display_name)
                 return self._send_json(200 if success else 400, {
                     "success": success,
                     "message": msg if success else None,
                     "error": msg if not success else None,
                     "cmd_preview": cmd_preview
                 })

        elif path == "/api/gpos/link":
            container_dn = data.get("container_dn", "")
            gpo_guid = data.get("gpo_guid", "")

            if not container_dn or not gpo_guid:
                return self._send_json(400, {"success": False, "error": "Container DN e GPO GUID são obrigatórios."})

            success, msg, cmd_preview = samba_svc.link_gpo(container_dn, gpo_guid)
            return self._send_json(200 if success else 400, {
                "success": success,
                "message": msg if success else None,
                "error": msg if not success else None,
                "cmd_preview": cmd_preview
            })

        return self._send_json(404, {"error": f"Rota POST não encontrada: '{path}'"})

    def do_DELETE(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.rstrip("/") if parsed_url.path != "/" else "/"
        data = self._read_body_json()

        if not self._check_auth():
            return self._send_json(401, {"success": False, "error": "Sessão expirada ou não autorizada."})

        if path == "/api/platform-users":
            username = data.get("username", "")
            if not username:
                return self._send_json(400, {"success": False, "error": "Nome do operador obrigatório."})
            success, msg = samba_svc.delete_platform_user(username)
            return self._send_json(200 if success else 400, {
                "success": success,
                "message": msg if success else None,
                "error": msg if not success else None
            })

        elif path == "/api/users":
            username = data.get("username", "")
            if not username:
                return self._send_json(400, {"success": False, "error": "Nome de usuário obrigatório."})
            success, msg, cmd_preview = samba_svc.delete_user(username)
            return self._send_json(200 if success else 400, {
                "success": success,
                "message": msg if success else None,
                "error": msg if not success else None,
                "cmd_preview": cmd_preview
            })

        elif path == "/api/computers":
            name = data.get("name", "")
            if not name:
                return self._send_json(400, {"success": False, "error": "Nome do computador obrigatório."})
            success, msg, cmd_preview = samba_svc.delete_computer(name)
            return self._send_json(200 if success else 400, {
                "success": success,
                "message": msg if success else None,
                "error": msg if not success else None,
                "cmd_preview": cmd_preview
            })

        elif path == "/api/ous":
            ou_dn = data.get("dn", "")
            if not ou_dn:
                return self._send_json(400, {"success": False, "error": "DN da OU é obrigatório."})
            success, msg, cmd_preview = samba_svc.delete_ou(ou_dn)
            return self._send_json(200 if success else 400, {
                "success": success,
                "message": msg if success else None,
                "error": msg if not success else None,
                "cmd_preview": cmd_preview
            })

        elif path == "/api/gpos/link":
            container_dn = data.get("container_dn", "")
            gpo_guid = data.get("gpo_guid", "")

            if not container_dn or not gpo_guid:
                return self._send_json(400, {"success": False, "error": "Container DN e GPO GUID são obrigatórios."})

            success, msg, cmd_preview = samba_svc.unlink_gpo(container_dn, gpo_guid)
            return self._send_json(200 if success else 400, {
                "success": success,
                "message": msg if success else None,
                "error": msg if not success else None,
                "cmd_preview": cmd_preview
            })

        elif path == "/api/objects":
            object_dn = data.get("dn", "")
            object_type = data.get("type", "user")
            if not object_dn:
                return self._send_json(400, {"success": False, "error": "DN do objeto é obrigatório."})
            success, msg, cmd_preview = samba_svc.delete_object_in_ou(object_dn, object_type)
            return self._send_json(200 if success else 400, {
                "success": success,
                "message": msg if success else None,
                "error": msg if not success else None,
                "cmd_preview": cmd_preview
            })

        return self._send_json(404, {"error": f"Rota DELETE não encontrada: '{path}'"})

def run_server():
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    
    # BIND EXCLUSIVO EM 127.0.0.1 (Somente Nginx aciona)
    with socketserver.TCPServer(("127.0.0.1", PORT), SambaHandler) as httpd:
        print(f"🚀 Backend iniciado localmente na porta {PORT} (Apenas conexões do Nginx)")
        print(f"🌐 Servidor AD: {samba_svc.server_ip} ({samba_svc.domain_dn})")
        print(f"💡 Modo Atual: {'Simulação (Mock)' if samba_svc.mock_mode else 'Real (samba-tool)'}")
        print(f"🤖 Módulo de IA: {'Carregado' if ai_detector else 'Desativado/Indisponível'}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor finalizado pelo usuário.")

if __name__ == "__main__":
    run_server()