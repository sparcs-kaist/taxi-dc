from modules.dns_manager import DNSManager, validate_ip
from modules.mongo_manager import MongoManager
from typing import Tuple, Optional

class TaxiDevTools:
    def __init__(self):
        self.dns_manager = DNSManager()
        self.mongo_manager = MongoManager()
        
    def check_services(self) -> bool:
        """Check if required services are running"""
        if not self.dns_manager.is_container_running():
            print("Error: DNS service is not running")
            return False
        return True

    def list_entries(self):
        """List both DNS entries and MongoDB users"""
        print("\n=== DNS Entries ===")
        self.dns_manager.display_dns_entries()
        print("\n=== MongoDB Users ===")
        self.mongo_manager.list_users()

    def create_user(self, username: str, ip: str) -> bool:
        """Create both DNS entry and MongoDB user"""
        print(f"\nCreating user: {username}")
        
        # First create MongoDB user
        password = self.mongo_manager.create_user(username)
        if not password:
            print("Failed to create MongoDB user")
            return False
            
        # Then create DNS entry
        if not self.dns_manager.add_dns_entry(username, ip):
            print("Warning: MongoDB user created but DNS entry failed")
            print("Removing MongoDB user...")
            self.mongo_manager.remove_user(username)
            return False
            
        print("\nUser created successfully!")
        print(f"Username: {username}")
        print(f"Password: {password}")
        print(f"IP: {ip}")
        return True

    def edit_user(self, old_username: str, new_username: str = None, new_ip: str = None) -> bool:
        """Edit user details in both DNS and MongoDB"""
        if not new_username and not new_ip:
            print("Error: Must provide either new username or new IP")
            return False

        if new_username:
            # First update MongoDB
            new_password = self.mongo_manager.edit_user(old_username, new_username)
            if not new_password:
                print("Failed to update MongoDB user")
                return False
                
            # Then update DNS if IP is also changing
            if new_ip:
                if not self.dns_manager.edit_dns_entry(old_username, new_username, new_ip):
                    print("Warning: MongoDB updated but DNS update failed")
                    # Try to revert MongoDB change
                    self.mongo_manager.edit_user(new_username, old_username)
                    return False
            else:
                # Just update the DNS username
                if not self.dns_manager.edit_dns_entry(old_username, new_username):
                    print("Warning: MongoDB updated but DNS update failed")
                    # Try to revert MongoDB change
                    self.mongo_manager.edit_user(new_username, old_username)
                    return False
                    
            print(f"\nUser edited successfully!")
            print(f"New username: {new_username}")
            print(f"New password: {new_password}")
            if new_ip:
                print(f"New IP: {new_ip}")
            return True
            
        else:
            # Only updating IP in DNS
            return self.dns_manager.edit_dns_entry(old_username, new_ip=new_ip)

    def remove_user(self, username: str) -> bool:
        """Remove user from both DNS and MongoDB"""
        print(f"\nRemoving user: {username}")
        
        # First remove DNS entry
        dns_success = self.dns_manager.remove_dns_entry(username)
        if not dns_success:
            print("Failed to remove DNS entry")
            return False
            
        # Then remove MongoDB user
        mongo_success = self.mongo_manager.remove_user(username)
        if not mongo_success:
            print("Warning: DNS entry removed but MongoDB user removal failed")
            return False
            
        print(f"Successfully removed user: {username}")
        return True

def main():
    tools = TaxiDevTools()
    
    if not tools.check_services():
        print("Please ensure all required services are running")
        exit(1)

    while True:
        print("\nTaxi Development Tools")
        print("1. List all entries")
        print("2. Create new user")
        print("3. Edit user")
        print("4. Remove user")
        print("5. Exit")
        
        choice = input("> ")
        
        match choice:
            case "1":
                tools.list_entries()
                
            case "2":
                username = input("Enter username: ").strip()
                if not username:
                    print("Username cannot be empty")
                    continue
                    
                ip = input("Enter IP address (format: 10.251.1.X): ").strip()
                if not validate_ip(ip):
                    continue
                    
                tools.create_user(username, ip)
                
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
                        tools.edit_user(username, new_username=new_username)
                    case "2":
                        new_ip = input("Enter new IP (format: 10.251.1.X): ").strip()
                        if validate_ip(new_ip):
                            tools.edit_user(username, new_ip=new_ip)
                    case "3":
                        new_username = input("Enter new username: ").strip()
                        new_ip = input("Enter new IP (format: 10.251.1.X): ").strip()
                        if validate_ip(new_ip):
                            tools.edit_user(username, new_username=new_username, new_ip=new_ip)
                    case _:
                        print("Invalid option")
                
            case "4":
                username = input("Enter username to remove: ").strip()
                if not username:
                    print("Username cannot be empty")
                    continue
                    
                if input(f"Are you sure you want to remove {username}? (y/N): ").lower() == 'y':
                    tools.remove_user(username)
                
            case "5":
                print("Exiting...")
                break
                
            case _:
                print("Invalid option")

if __name__ == "__main__":
    main()