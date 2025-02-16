from typing import List, Tuple
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
        self.http_user = os.getenv("HTTP_USER", "admin")
        self.http_pass = os.getenv("HTTP_PASS", "password")
        self.network = "taxi-dc_shared-backend"
        self.backup_dir = Path("taxi-dns/dns_backups")
        self.backup_dir.mkdir(exist_ok=True)

    def _backup_config(self) -> str:
        """Create a backup of the current DNS config."""
        try:
            current_config = self._execute_docker_command("cat /etc/dnsmasq.conf")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_dir / f"dnsmasq_{timestamp}.conf"
            
            with open(backup_path, "w") as f:
                f.write(current_config)

            # Keep only the latest 10 backups
            backups = sorted(self.backup_dir.glob("dnsmasq_*.conf"))
            for old_backup in backups[:-10]:
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
        print("\nOptions:")
        print("1. List DNS entries")
        print("2. Add new DNS entry")
        print("3. Remove DNS entry")
        print("4. Exit")
        
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
                username = input("Enter username to remove: ").strip()
                dns_manager.remove_dns_entry(username)
            case "4":
                print("Exiting...")
                break
            case _:
                print("Invalid option")

if __name__ == "__main__":
    main()