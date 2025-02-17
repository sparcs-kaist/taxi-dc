from modules.dns_manager import DNSManager, validate_ip
from modules.mongo_manager import MongoManager
from modules.container_manager import ContainerManager
from typing import Tuple, Optional
from tabulate import tabulate

class TaxiDevCenter:
    def __init__(self):
        self.dns_manager = DNSManager()
        self.mongo_manager = MongoManager()
        self.container_manager = ContainerManager()

    def check_services(self) -> bool:
        """Check if required services are running"""
        if not self.dns_manager.is_container_running():
            print("Error: DNS service is not running")
            return False
        return True

    def list_entries(self):
        """List combined DNS, MongoDB, and Container entries in a single table"""
        # Get DNS entries
        dns_entries = {username: ip for username, ip in self.dns_manager.parse_dns_entries()}
        
        # Get MongoDB users
        mongo_cmd = f'db.getSiblingDB("{self.mongo_manager.env["MONGO_INITDB_DATABASE"]}").getUsers()'
        mongo_users = self.mongo_manager._execute_mongo_command(mongo_cmd, return_json=True)
        mongo_info = {}
        if mongo_users:
            for user in mongo_users:
                username = user['user']
                roles = [f"{role['role']}@{role['db']}" for role in user.get('roles', [])]
                mongo_info[username] = f"{', '.join(roles)} ({user['db']})"

        # Get Container status
        container_users = self.container_manager.list_users()
        container_status = {}
        for username in container_users:
            status = "Running" if self.container_manager.check_container_exists(username) else "Not Running"
            container_status[username] = f"taxi-{username} ({status})"

        # Combine all unique usernames
        all_usernames = sorted(set(list(dns_entries.keys()) + list(mongo_info.keys()) + list(container_status.keys())))
        
        # Create combined table data
        table_data = []
        for username in all_usernames:
            row = [
                username,
                dns_entries.get(username, "No DNS entry"),
                mongo_info.get(username, "No MongoDB user"),
                container_status.get(username, "No Container")
            ]
            table_data.append(row)

        # Print combined table
        print("\nSystem Entries:")
        headers = ["Username", "DNS Entry", "MongoDB Roles", "Container"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))

        # Print summary
        print(f"\nTotal entries: {len(all_usernames)}")
        print(f"Containers: {len(container_status)}")
        print(f"DNS entries: {len(dns_entries)}")
        print(f"MongoDB users: {len(mongo_info)}")

    def create_user(self, username: str, ip: str) -> bool:
        """Create user across all services"""
        print(f"\nCreating user: {username}")
        
        # First create DNS entry
        if not self.dns_manager.add_dns_entry(username, ip):
            print("Failed to create DNS entry")
            return False
            
        # Then create MongoDB user
        mongo_password = self.mongo_manager.create_user(username)
        if not mongo_password:
            print("Failed to create MongoDB user")
            # Rollback DNS entry
            self.dns_manager.remove_dns_entry(username)
            return False

        # Finally create container
        try:
            ssh_password = self.container_manager.add_user(username, ip, mongo_password)
            if not ssh_password:
                print("Failed to create container")
                # Rollback previous operations
                self.dns_manager.remove_dns_entry(username)
                self.mongo_manager.remove_user(username)
                return False

            print("\nUser created successfully!")
            print(f"Username: {username}")
            print(f"IP: {ip}")
            print(f"SSH Password: {ssh_password}")
            print("Please save these credentials!")
            return True

        except Exception as e:
            print(f"Error creating container: {e}")
            # Rollback previous operations
            self.dns_manager.remove_dns_entry(username)
            self.mongo_manager.remove_user(username)
            return False

    def edit_user(self, old_username: str, new_username: str = None, new_ip: str = None) -> bool:
        """Edit user details across all services"""
        if not new_username and not new_ip:
            print("Error: Must provide either new username or new IP")
            return False

        # Store old values for rollback
        if new_username:
            # Edit MongoDB first (it's most critical)
            new_mongo_password = self.mongo_manager.edit_user(old_username, new_username)
            if not new_mongo_password:
                print("Failed to update MongoDB user")
                return False

            # Then edit DNS
            if not self.dns_manager.edit_dns_entry(old_username, new_username, new_ip):
                print("Failed to update DNS entry")
                # Rollback MongoDB
                self.mongo_manager.edit_user(new_username, old_username)
                return False

            # Finally edit container
            try:
                if not self.container_manager.edit_user(old_username, new_username, new_ip):
                    print("Failed to update container")
                    # Rollback previous operations
                    self.mongo_manager.edit_user(new_username, old_username)
                    self.dns_manager.edit_dns_entry(new_username, old_username, None)
                    return False
            except Exception as e:
                print(f"Error updating container: {e}")
                # Rollback previous operations
                self.mongo_manager.edit_user(new_username, old_username)
                self.dns_manager.edit_dns_entry(new_username, old_username, None)
                return False

        else:
            # Only updating IP
            if not self.dns_manager.edit_dns_entry(old_username, new_ip=new_ip):
                print("Failed to update DNS entry")
                return False

            try:
                if not self.container_manager.edit_user(old_username, new_ip=new_ip):
                    print("Failed to update container")
                    # Rollback DNS
                    self.dns_manager.edit_dns_entry(old_username, new_ip=None)
                    return False
            except Exception as e:
                print(f"Error updating container: {e}")
                # Rollback DNS
                self.dns_manager.edit_dns_entry(old_username, new_ip=None)
                return False

        print("\nUser updated successfully!")
        if new_username:
            print(f"New username: {new_username}")
        if new_ip:
            print(f"New IP: {new_ip}")
        return True

    def remove_user(self, username: str) -> bool:
        """Remove user from all services"""
        print(f"\nRemoving user: {username}")
        
        # Remove container first
        if not self.container_manager.remove_user(username):
            print("Failed to remove container")
            return False
            
        # Then remove DNS entry
        if not self.dns_manager.remove_dns_entry(username):
            print("Failed to remove DNS entry")
            return False
            
        # Finally remove MongoDB user
        if not self.mongo_manager.remove_user(username):
            print("Failed to remove MongoDB user")
            return False
            
        print(f"Successfully removed user: {username}")
        return True

def main():
    manager = TaxiDevCenter()
    
    if not manager.check_services():
        print("Please ensure all required services are running")
        exit(1)

    while True:
        print("\nTaxi Management System")
        print("1. List all entries")
        print("2. Create new user")
        print("3. Edit user")
        print("4. Remove user")
        print("5. Exit")
        
        choice = input("> ")
        
        match choice:
            case "1":
                manager.list_entries()
                
            case "2":
                username = input("Enter username: ").strip()
                if not username:
                    print("Username cannot be empty")
                    continue
                    
                ip = input("Enter IP address (format: 10.251.1.X): ").strip()
                if not validate_ip(ip):
                    continue
                    
                manager.create_user(username, ip)
                
            case "3":
                username = input("Enter current username: ").strip()
                if not username:
                    print("Username cannot be empty")
                    continue
                    
                print("\nWhat would you like to edit?")
                print("1. Username")
                print("2. IP address")
                print("3. Both")
                edit_choice = input("> ").strip()
                
                match edit_choice:
                    case "1":
                        new_username = input("Enter new username: ").strip()
                        if new_username:
                            manager.edit_user(username, new_username=new_username)
                    case "2":
                        new_ip = input("Enter new IP (format: 10.251.1.X): ").strip()
                        if validate_ip(new_ip):
                            manager.edit_user(username, new_ip=new_ip)
                    case "3":
                        new_username = input("Enter new username: ").strip()
                        new_ip = input("Enter new IP (format: 10.251.1.X): ").strip()
                        if validate_ip(new_ip):
                            manager.edit_user(username, new_username=new_username, new_ip=new_ip)
                    case _:
                        print("Invalid option")
                
            case "4":
                username = input("Enter username to remove: ").strip()
                if not username:
                    print("Username cannot be empty")
                    continue
                    
                if input(f"Are you sure you want to remove {username}? (y/N): ").lower() == 'y':
                    manager.remove_user(username)
                
            case "5":
                print("Exiting...")
                break
                
            case _:
                print("Invalid option")

if __name__ == "__main__":
    main()