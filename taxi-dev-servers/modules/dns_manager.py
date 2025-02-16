from typing import List, Tuple, Dict
import re
import subprocess
import os
from tabulate import tabulate
import time
from datetime import datetime
from pathlib import Path
import shutil

class DNSManager:
    def __init__(self, container_name: str = "taxi-dns"):
        self.container_name = container_name
        self.root_dir = Path(__file__).parent.parent.parent
        self.env = self._load_env()
        self.http_user = self.env.get("HTTP_USER", "admin")
        self.http_pass = self.env.get("HTTP_PASS", "password")
        self.network = "taxi-dc_shared-backend"
        self.backup_dir = self.root_dir / "taxi-dns" / "dns_backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _load_env(self) -> Dict[str, str]:
        """Load environment variables from .env file"""
        env_dict = {}
        env_path = self.root_dir / ".env"

        if not env_path.exists():
            raise FileNotFoundError(f"Error: .env file not found at {env_path}!")
            
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    env_dict[key] = value
                    
        return env_dict

    def _backup_config(self) -> str:
        """Create a backup of the current DNS config."""
        try:
            current_config = self._execute_docker_command("cat /etc/dnsmasq.conf")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_dir / f"dnsmasq_{timestamp}.conf"
            
            with open(backup_path, "w") as f:
                f.write(current_config)

            # Keep only the latest 100 backups
            backups = sorted(self.backup_dir.glob("dnsmasq_*.conf"))
            for old_backup in backups[:-100]:
                old_backup.unlink()

            return current_config
        except Exception as e:
            print(f"Warning: Failed to create backup: {e}")
            return ""

    def _restore_config(self, config: str) -> bool:
        """Restore DNS config from a backup."""
        try:
            # Write the backup content to a temporary file
            with open("/tmp/dnsmasq_restore.conf", "w") as f:
                f.write(config)

            # Copy the file into the container
            subprocess.run(
                f"docker cp /tmp/dnsmasq_restore.conf {self.container_name}:/etc/dnsmasq.conf",
                shell=True, check=True, capture_output=True
            )

            # Cleanup
            os.unlink("/tmp/dnsmasq_restore.conf")

            # Restart DNS
            return self._restart_dns()
        except Exception as e:
            print(f"Error during restore: {e}")
            return False

    def is_container_running(self) -> bool:
        try:
            cmd = f"docker container inspect -f '{{{{.State.Running}}}}' {self.container_name}"
            result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
            return result.stdout.strip().lower() == 'true'
        except subprocess.CalledProcessError:
            return False

    def _execute_docker_command(self, command: str) -> str:
        docker_cmd = f"docker exec {self.container_name} /bin/sh -c '{command}'"
        result = subprocess.run(docker_cmd, shell=True, check=True, capture_output=True, text=True)
        return result.stdout

    def _restart_dns(self) -> bool:
        restart_cmd = (
            f'docker run --rm --network {self.network} curlimages/curl:8.1.2 '
            f'-X PUT -u {self.http_user}:{self.http_pass} '
            f'http://taxi-dns:8080/restart'
        )
        try:
            subprocess.run(restart_cmd, shell=True, check=True, capture_output=True)
            time.sleep(2)  # Allow time for restart
            return True
        except subprocess.CalledProcessError:
            return False

    def parse_dns_entries(self) -> List[Tuple[str, str]]:
        try:
            content = self._execute_docker_command("cat /etc/dnsmasq.conf")
            pattern = r'address=/([^/]+)\.taxi\.sparcs\.org/(\d+\.\d+\.\d+\.\d+)'
            matches = re.finditer(pattern, content)
            
            entries = [
                (match.group(1), match.group(2))
                for match in matches
                if match.group(1) != "shared-mongo"
            ]
            return sorted(entries)
        except subprocess.CalledProcessError:
            return []

    def display_dns_entries(self):
        entries = self.parse_dns_entries()
        if not entries:
            print("No DNS entries found")
            return
        print(tabulate(entries, headers=["Username", "IP"], tablefmt="grid"))

    def is_entry_taken(self, username: str, ip: str) -> tuple[bool, str]:
        entries = self.parse_dns_entries()
        for stored_username, stored_ip in entries:
            if stored_ip == ip:
                return True, f"Error: IP {ip} is already in use"
            if stored_username == username:
                return True, f"Error: Username {username} is already in use"
        return False, ""

    def _verify_dns_entry(self, username: str) -> bool:
        try:
            verify_cmd = (
                f"docker run --rm --network {self.network} busybox:1.36 "
                f"nslookup {username}.taxi.sparcs.org taxi-dns"
            )
            result = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True)
            return "Name or service not known" not in result.stderr
        except subprocess.CalledProcessError:
            return False

    def add_dns_entry(self, username: str, ip: str) -> bool:
        is_taken, error_msg = self.is_entry_taken(username, ip)
        if is_taken:
            print(error_msg)
            return False

        # Backup current config
        backup_config = self._backup_config()
        if not backup_config:
            print("Warning: Failed to create backup before adding entry")
            return False

        try:
            dns_entry = f"address=/{username}.taxi.sparcs.org/{ip}"
            self._execute_docker_command(f'echo "{dns_entry}" >> /etc/dnsmasq.conf')

            if not self._restart_dns():
                print("Failed to restart DNS service, rolling back changes...")
                self._restore_config(backup_config)
                return False

            if self._verify_dns_entry(username):
                print(f"Successfully added DNS entry for {username}")
                return True
            else:
                print("DNS entry added but not resolving correctly, rolling back changes...")
                self._restore_config(backup_config)
                return False

        except subprocess.CalledProcessError as e:
            print(f"Failed to add DNS entry: {e}")
            print("Rolling back changes...")
            self._restore_config(backup_config)
            return False

    def remove_dns_entry(self, username: str) -> bool:
        entries = self.parse_dns_entries()
        if not any(entry[0] == username for entry in entries):
            print(f"Error: No DNS entry found for username {username}")
            return False

        # Backup current config
        backup_config = self._backup_config()
        if not backup_config:
            print("Warning: Failed to create backup before removing entry")
            return False

        try:
            # Remove entry
            user_pattern = f"{username}.taxi.sparcs.org"
            remove_cmd = (
                f'grep -v "address=/{user_pattern}/" /etc/dnsmasq.conf > /tmp/dnsmasq.conf.tmp && '
                f'cat /tmp/dnsmasq.conf.tmp > /etc/dnsmasq.conf && '
                f'rm /tmp/dnsmasq.conf.tmp'
            )
            self._execute_docker_command(remove_cmd)

            # Restart DNS
            if not self._restart_dns():
                print("Failed to restart DNS service, rolling back changes...")
                self._restore_config(backup_config)
                return False

            print(f"Successfully removed DNS entry for {username}")
            return True

        except subprocess.CalledProcessError as e:
            print(f"Failed to remove DNS entry: {e}")
            print("Rolling back changes...")
            self._restore_config(backup_config)
            return False

    def edit_dns_entry(self, old_username: str, new_username: str = None, new_ip: str = None) -> bool:
        """Edit a DNS entry by changing username and/or IP."""
        if not new_username and not new_ip:
            print("Error: Must provide either new username or new IP")
            return False

        entries = self.parse_dns_entries()
        old_entry = next((entry for entry in entries if entry[0] == old_username), None)
        
        if not old_entry:
            print(f"Error: No DNS entry found for username {old_username}")
            return False

        current_ip = old_entry[1]
        new_entry_username = new_username or old_username
        new_entry_ip = new_ip or current_ip

        # Check if new values conflict with existing entries
        for entry in entries:
            stored_username, stored_ip = entry
            if stored_username == old_username:
                continue  # Skip checking against self
            
            if new_username and stored_username == new_username:
                print(f"Error: Username {new_username} is already in use")
                return False
                
            if new_ip and stored_ip == new_ip:
                print(f"Error: IP {new_ip} is already in use")
                return False

        # Backup current config
        backup_config = self._backup_config()
        if not backup_config:
            print("Warning: Failed to create backup before editing entry")
            return False

        try:
            # Remove old entry
            user_pattern = f"{old_username}.taxi.sparcs.org"
            remove_cmd = (
                f'grep -v "address=/{user_pattern}/" /etc/dnsmasq.conf > /tmp/dnsmasq.conf.tmp && '
                f'cat /tmp/dnsmasq.conf.tmp > /etc/dnsmasq.conf && '
                f'rm /tmp/dnsmasq.conf.tmp'
            )
            self._execute_docker_command(remove_cmd)

            # Add new entry
            dns_entry = f"address=/{new_entry_username}.taxi.sparcs.org/{new_entry_ip}"
            self._execute_docker_command(f'echo "{dns_entry}" >> /etc/dnsmasq.conf')

            # Restart DNS
            if not self._restart_dns():
                print("Failed to restart DNS service, rolling back changes...")
                self._restore_config(backup_config)
                return False

            # Verify new entry
            if self._verify_dns_entry(new_entry_username):
                changes = []
                if new_username:
                    changes.append(f"username: {old_username} -> {new_username}")
                if new_ip:
                    changes.append(f"IP: {current_ip} -> {new_ip}")
                print(f"Successfully edited DNS entry: {', '.join(changes)}")
                return True
            else:
                print("DNS entry modified but not resolving correctly, rolling back changes...")
                self._restore_config(backup_config)
                return False

        except subprocess.CalledProcessError as e:
            print(f"Failed to edit DNS entry: {e}")
            print("Rolling back changes...")
            self._restore_config(backup_config)
            return False

def validate_ip(ip: str) -> bool:
    pattern = r'^10\.251\.1\.\d+$'
    if not re.match(pattern, ip):
        print("Error: IP must be in format 10.251.1.X")
        return False
    
    last_octet = int(ip.split('.')[-1])
    if last_octet < 1 or last_octet > 254:
        print("Error: Last IP octet must be between 1 and 254")
        return False
    return True

def main():
    dns_manager = DNSManager()

    if not dns_manager.is_container_running():
        print(f"Error: Docker container '{dns_manager.container_name}' is not running")
        print("Please make sure the container is up and running using 'docker ps'")
        exit(1)

    while True:
        print("\nDNS Management Options:")
        print("1. List DNS entries")
        print("2. Add new DNS entry")
        print("3. Edit DNS entry")
        print("4. Remove DNS entry")
        print("5. Exit")
        
        choice = input("> ")

        match choice:
            case "1":
                dns_manager.display_dns_entries()
                
            case "2":
                username = input("Enter username: ").strip()
                ip = input("Enter IP address (format: 10.251.1.X): ").strip()
                if validate_ip(ip):
                    dns_manager.add_dns_entry(username, ip)
                    
            case "3":
                # First display current entries
                print("\nCurrent DNS entries:")
                dns_manager.display_dns_entries()
                
                username = input("\nEnter username to edit: ").strip()
                print("\nWhat would you like to edit?")
                print("1. Username only")
                print("2. IP address only")
                print("3. Both username and IP")
                
                edit_choice = input("> ").strip()
                match edit_choice:
                    case "1":
                        new_username = input("Enter new username: ").strip()
                        if new_username:
                            dns_manager.edit_dns_entry(username, new_username=new_username)
                            
                    case "2":
                        new_ip = input("Enter new IP (format: 10.251.1.X): ").strip()
                        if validate_ip(new_ip):
                            dns_manager.edit_dns_entry(username, new_ip=new_ip)
                            
                    case "3":
                        new_username = input("Enter new username: ").strip()
                        new_ip = input("Enter new IP (format: 10.251.1.X): ").strip()
                        if new_username and validate_ip(new_ip):
                            dns_manager.edit_dns_entry(username, new_username=new_username, new_ip=new_ip)
                            
                    case _:
                        print("Invalid edit option")
                
            case "4":
                username = input("Enter username to remove: ").strip()
                if username:
                    confirm = input(f"Are you sure you want to remove {username}? (y/N): ").lower()
                    if confirm == 'y':
                        dns_manager.remove_dns_entry(username)
                
            case "5":
                print("Exiting...")
                break
                
            case _:
                print("Invalid option")

if __name__ == "__main__":
    main()