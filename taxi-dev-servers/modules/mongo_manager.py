from typing import Optional, Dict
import subprocess
import base64
import os
from pathlib import Path
import re
import json
from tabulate import tabulate


class MongoManager:
    def __init__(self, container_name: str = "taxi-mongo-shared"):
        self.container_name = container_name
        self.root_dir = Path(__file__).parent.parent.parent
        self.env = self._load_env() 

    def _load_env(self) -> Dict[str, str]:
        """Load environment variables from .env file"""
        env_dict = {}
        env_path = self.root_dir / ".env"
        
        if not env_path.exists():
            raise FileNotFoundError("Error: .env file not found!")
            
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    env_dict[key] = value
                    
        return env_dict

    def _generate_password(self) -> str:
        """Generate a secure random password"""
        try:
            result = subprocess.run(
                ["openssl", "rand", "-base64", "48"],
                capture_output=True,
                text=True,
                check=True
            )
            # Clean up the password (remove newlines and limit length)
            password = re.sub(r'[^a-zA-Z0-9]', '', result.stdout)[:32]
            return password
        except subprocess.CalledProcessError as e:
            print(f"Error generating password: {e}")
            raise

    def _execute_mongo_command(self, mongo_command: str, return_json: bool = False) -> Optional[str]:
        """Execute a MongoDB command in the container"""
        # Add .toArray() for list commands to get proper JSON
        if return_json:
            mongo_command = f"JSON.stringify({mongo_command})"

        cmd = f"""docker exec -i {self.container_name} mongo \
                 -u "{self.env['MONGO_ROOT_USERNAME']}" \
                 -p "{self.env['MONGO_ROOT_PASSWORD']}" \
                 --authenticationDatabase admin \
                 --quiet \
                 --eval '{mongo_command}'"""
                 
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
            if return_json:
                # Try to parse JSON from the output
                try:
                    return json.loads(result.stdout.strip())
                except json.JSONDecodeError:
                    print("Failed to parse MongoDB output as JSON")
                    return None
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"Error executing MongoDB command: {e}")
            print(f"Error output: {e.stderr}")
            return None

    def list_users(self) -> bool:
        """List all MongoDB users in a formatted table"""
        try:
            # MongoDB command to list users
            list_cmd = (
                f'db.getSiblingDB("{self.env["MONGO_INITDB_DATABASE"]}")'
                '.getUsers()'
            )
            
            users = self._execute_mongo_command(list_cmd, return_json=True)
            if not users:
                print("No users found or error retrieving users")
                return False

            # Extract relevant information for the table
            user_info = []
            for user in users:
                roles = [f"{role['role']}@{role['db']}" for role in user.get('roles', [])]
                user_info.append({
                    'Username': user['user'],
                    'Database': user['db'],
                    'Roles': ', '.join(roles)
                })

            if user_info:
                # Print version info
                version = self._execute_mongo_command('db.version()')
                if version:
                    print(f"\nMongoDB Version: {version.strip()}")
                
                # Print users table
                print("\nDatabase Users:")
                print(tabulate(user_info, headers='keys', tablefmt='grid'))
                return True
            else:
                print("No users found")
                return False
            
        except Exception as e:
            print(f"Failed to list MongoDB users: {e}")
            return False

    def create_user(self, username: str) -> Optional[str]:
        """Create a new MongoDB user with generated password"""
        try:
            # First check if user exists
            users = self._execute_mongo_command(
                f'db.getSiblingDB("{self.env["MONGO_INITDB_DATABASE"]}").getUsers()',
                return_json=True
            )
            
            if users and any(user['user'] == username for user in users):
                print(f"Error: User '{username}' already exists")
                return None

            # Generate password
            password = self._generate_password()
            
            # MongoDB command to create user
            create_cmd = (
                f'db.getSiblingDB("{self.env["MONGO_INITDB_DATABASE"]}").createUser('
                f'{{"user": "{username}", '
                f'"pwd": "{password}", '
                f'roles: [{{ role: "dbOwner", db: "{username}" }}]}});'
            )
            
            result = self._execute_mongo_command(create_cmd)
            if result and "Successfully added user" in result:
                print(f"Successfully created MongoDB user: {username}")
                return password
            return None
            
        except Exception as e:
            print(f"Failed to create MongoDB user: {e}")
            return None

    def remove_user(self, username: str) -> bool:
        """Remove a MongoDB user"""
        try:
            # First check if user exists
            users = self._execute_mongo_command(
                f'db.getSiblingDB("{self.env["MONGO_INITDB_DATABASE"]}").getUsers()',
                return_json=True
            )
            
            if not users or not any(user['user'] == username for user in users):
                print(f"Error: User '{username}' does not exist")
                return False

            # MongoDB command to remove user
            remove_cmd = (
                f'db.getSiblingDB("{self.env["MONGO_INITDB_DATABASE"]}")'
                f'.dropUser("{username}");'
            )
            
            result = self._execute_mongo_command(remove_cmd)
            if result is not None:
                print(f"Successfully removed MongoDB user: {username}")
                return True
            return False
            
        except Exception as e:
            print(f"Failed to remove MongoDB user: {e}")
            return False

    def edit_user(self, old_username: str, new_username: str) -> Optional[str]:
        """Change a MongoDB username"""
        try:
            # First check if old user exists and new username doesn't
            users = self._execute_mongo_command(
                f'db.getSiblingDB("{self.env["MONGO_INITDB_DATABASE"]}").getUsers()',
                return_json=True
            )
            
            if not users or not any(user['user'] == old_username for user in users):
                print(f"Error: User '{old_username}' does not exist")
                return None

            if any(user['user'] == new_username for user in users):
                print(f"Error: User '{new_username}' already exists")
                return None

            # Generate new password for security
            new_password = self._generate_password()

            # Create new user with same roles
            old_user = next(user for user in users if user['user'] == old_username)
            roles = old_user.get('roles', [])
            
            # Update roles to use new username for dbOwner
            updated_roles = []
            for role in roles:
                if role['role'] == 'dbOwner' and role['db'] == old_username:
                    updated_roles.append({'role': 'dbOwner', 'db': new_username})
                else:
                    updated_roles.append(role)

            # Create new user
            create_cmd = (
                f'db.getSiblingDB("{self.env["MONGO_INITDB_DATABASE"]}").createUser('
                f'{{"user": "{new_username}", '
                f'"pwd": "{new_password}", '
                f'roles: {json.dumps(updated_roles)}}});'
            )
            
            create_result = self._execute_mongo_command(create_cmd)
            if not create_result or "Successfully added user" not in create_result:
                print("Failed to create new user")
                return None

            # Remove old user
            remove_cmd = (
                f'db.getSiblingDB("{self.env["MONGO_INITDB_DATABASE"]}")'
                f'.dropUser("{old_username}");'
            )
            
            remove_result = self._execute_mongo_command(remove_cmd)
            if remove_result is not None:
                print(f"Successfully renamed user from '{old_username}' to '{new_username}'")
                return new_password
            
            # If we get here, something went wrong with removing the old user
            print("Warning: New user created but failed to remove old user")
            return new_password

        except Exception as e:
            print(f"Failed to edit MongoDB user: {e}")
            return None

def main():
    mongo_manager = MongoManager()
    
    while True:
        print("\nMongoDB User Management:")
        print("1. List users")
        print("2. Create new user")
        print("3. Edit user")
        print("4. Remove user")
        print("5. Exit")
        
        choice = input("> ")
        
        match choice:
            case "1":
                mongo_manager.list_users()
                
            case "2":
                username = input("Enter username: ").strip()
                if not username:
                    print("Username cannot be empty")
                    continue
                    
                password = mongo_manager.create_user(username)
                if password:
                    print(f"User created successfully.")
                    print(f"Username: {username}")
                    print(f"Password: {password}")
                    print("Please save these credentials!")
                    
            case "3":
                # First display current users
                print("\nCurrent MongoDB users:")
                mongo_manager.list_users()
                
                old_username = input("\nEnter username to edit: ").strip()
                if not old_username:
                    print("Username cannot be empty")
                    continue
                    
                new_username = input("Enter new username: ").strip()
                if not new_username:
                    print("New username cannot be empty")
                    continue
                
                if old_username == new_username:
                    print("New username must be different from current username")
                    continue
                    
                password = mongo_manager.edit_user(old_username, new_username)
                if password:
                    print(f"User edited successfully.")
                    print(f"New username: {new_username}")
                    print(f"New password: {password}")
                    print("Please save these credentials!")
                    
            case "4":
                username = input("Enter username to remove: ").strip()
                if not username:
                    print("Username cannot be empty")
                    continue
                    
                confirm = input(f"Are you sure you want to remove {username}? (y/N): ").lower()
                if confirm == 'y':
                    if mongo_manager.remove_user(username):
                        print(f"User {username} removed successfully")
                    
            case "5":
                print("Exiting...")
                break
                
            case _:
                print("Invalid option")

if __name__ == "__main__":
    main()