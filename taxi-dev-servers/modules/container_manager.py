import os
import subprocess
import tempfile
import shutil
from pathlib import Path
import random
import string
import yaml
from typing import Dict
import shlex

class ContainerManager:
    def __init__(self):
        self.root_dir = Path(__file__).parent.parent.parent
        self.env = self._load_env()
        self.compose_dir = self.root_dir / "taxi-dev-servers" / "docker-compose-files"
        self.temp_env_dir = self.root_dir / "taxi-dev-servers" / "temp-env-files"
        self.template_path = self.root_dir / 'docker-compose.private.template.yaml'
        self.build_dir =  self.root_dir / "taxi-dev-servers"
        self.compose_dir.mkdir(exist_ok=True)
        self.temp_env_dir.mkdir(exist_ok=True)

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

    def _generate_password(self, length=16) -> str:
        """Generate a secure password"""
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(random.choice(chars) for _ in range(length))
    
    def create_env_files(self, username: str, mongo_password: str):
        """Reads .env files, modifies only DB_PATH, and stores them temporarily."""
        env_files = {
            "development": self.root_dir / ".env.back.development",
            "test": self.root_dir / ".env.back.test",
        }
        
        dev_user = username  
        
        modified_env_paths = {}

        for env_name, env_path in env_files.items():
            if not env_path.exists():
                raise FileNotFoundError(f"⚠️ Error: {env_path} not found!")

            temp_env_path = self.temp_env_dir / f".env.back.{env_name}.{username}"

            with open(env_path, "r") as file:
                lines = file.readlines()

            with open(temp_env_path, "w") as file:
                for line in lines:
                    if line.startswith("DB_PATH="):
                        new_db_path = f"DB_PATH=mongodb://{dev_user}:{mongo_password}@taxi-mongo-shared:27017/{dev_user}?authSource=dev"
                        file.write(new_db_path + "\n")
                    else:
                        file.write(line)

            modified_env_paths[env_name] = temp_env_path

        return modified_env_paths["development"], modified_env_paths["test"]

    def build_base_image(self):
        """Build the base Docker image"""
        print("🔨 Building base image...")
        dockerfile_base_path = self.build_dir / 'Dockerfile.base'
        
        if not dockerfile_base_path.exists():
            raise FileNotFoundError(f"Base Dockerfile not found at {dockerfile_base_path}")
            
        subprocess.run([
            'docker', 'build',
            '-f', str(dockerfile_base_path),  # Use full path to Dockerfile.base
            '-t', 'taxi-base',
            str(self.build_dir)
        ], check=True)
        print("✅ Built base image: taxi-base")

    def build_image(self, username: str, password: str, mongo_password: str):
        """Build the Docker image for a specific user"""
        try:
            subprocess.run(['docker', 'image', 'inspect', 'taxi-base'], 
                        check=True, capture_output=True)
        except subprocess.CalledProcessError:
            self.build_base_image()

        try:
            # Create temporary env files
            env_back_dev, env_back_test = self.create_env_files(username, mongo_password)
            env_front = self.root_dir / ".env.front"

            # Read the content of the env files
            with open(env_back_dev, 'r') as f:
                env_back_dev_content = f.read()
            with open(env_back_test, 'r') as f:
                env_back_test_content = f.read()
            with open(env_front, 'r') as f:
                env_front_content = f.read()

            print(f"🔨 Building image for {username}...")
            subprocess.run([
                'docker', 'build',
                '--build-arg', f'UBUNTU_PASSWORD={password}',
                '--build-arg', f'DEV_USER={username}',
                "--build-arg", f"ENV_BACK_DEV={env_back_dev_content}",
                "--build-arg", f"ENV_BACK_TEST={env_back_test_content}",
                "--build-arg", f"ENV_FRONT={env_front_content}",
                '-t', f'taxi-{username}',
                str(self.build_dir)
            ], check=True)
            print(f"✅ Built image: taxi-{username}")

        finally:
            # Clean up temporary env files
            if env_back_dev and env_back_dev.exists():
                env_back_dev.unlink()
            if env_back_test and env_back_test.exists():
                env_back_test.unlink()
            print(f"🧹 Cleaned up temporary environment files for {username}")

    def load_template(self, values: Dict[str, str]) -> str:
        """Load and populate the template with values"""
        if not self.template_path.exists():
            raise FileNotFoundError(f"{self.template_path} does not exist")

        with open(self.template_path, 'r') as f:
            template_str = f.read()

        # Replace placeholders with values
        for key, value in values.items():
            template_str = template_str.replace(f"{{{{ {key} }}}}", str(value))

        return template_str
    
    def check_container_exists(self, username: str) -> bool:
        """Check if container already exists"""
        cmd = f"docker ps -a --format '{{{{.Names}}}}' | grep -q '^taxi-{username}$'"
        return subprocess.run(cmd, shell=True).returncode == 0

    def check_image_exists(self, image_name: str) -> bool:
        """Check if Docker image exists"""
        cmd = f"docker image inspect {image_name} >/dev/null 2>&1"
        return subprocess.run(cmd, shell=True).returncode == 0

    def add_user(self, username: str, ipv4_address: str, mongo_password: str):
        """Add a new user container with a unique password"""
        if self.check_container_exists(username):
            print(f"⚠️ Container for {username} already exists")
            return False

        image_name = f'taxi-{username}'
        if self.check_image_exists(image_name):
            print(f"⚠️ Image {image_name} already exists, will be rebuilt")
            try:
                subprocess.run(['docker', 'rmi', image_name], check=True)
                print(f"Removed existing image {image_name}")
            except subprocess.CalledProcessError as e:
                print(f"Failed to remove existing image: {e}")
                return False
                
        password = self._generate_password()

        # Build user-specific Docker image first
        self.build_image(username, password, mongo_password)

        # Create compose file
        compose_values = {
            "username": username,
            "ipv4_address": ipv4_address
        }
        compose_content = self.load_template(compose_values)
        compose_file = self.compose_dir / f"docker-compose.{username}.yml"
        compose_file.write_text(compose_content)

        # Start container
        subprocess.run([
            'docker', 'compose', 
            '-f', str(compose_file),
            'up',
            '-d'
        ], check=True)

        print(f"🚀 Added and started container for {username} (password stored internally).")
        return password

    def list_users(self):
        """List all current users"""
        return [f.stem.replace('docker-compose.', '') 
                for f in self.compose_dir.glob('docker-compose.*.yml')]
    
    def remove_user(self, username: str):
        """Remove a user's container"""
        compose_file = self.compose_dir / f"docker-compose.{username}.yml"

        if not compose_file.exists():
            print(f"⚠️ No configuration found for {username}")
            return False

        # Stop and remove container
        subprocess.run([
            'docker', 'compose',
            '-f', str(compose_file),
            'down'
        ], check=True)

        # Remove compose file
        compose_file.unlink()
        print(f"🗑 Removed container and configuration for {username}")

        # Remove built image
        subprocess.run(['docker', 'rmi', f'taxi-{username}'], check=True)
        print(f"🗑 Removed Docker image for {username}")

        # Remove user directory if it exists - using sudo
        user_dir = self.root_dir / "taxi-dev-servers" / "users" / username
        if user_dir.exists():
            try:
                subprocess.run(['sudo', 'rm', '-rf', str(user_dir)], check=True)
                print(f"🗑 Removed user directory for {username}")
            except subprocess.CalledProcessError as e:
                print(f"⚠️ Failed to remove user directory: {e}")

        # Remove temp env files if they exist
        for env_file in self.temp_env_dir.glob(f"*.{username}"):
            env_file.unlink()
        print(f"🗑 Removed temporary environment files for {username}")

        return True

def main():
    manager = ContainerManager()
    
    while True:
        print("\nContainer Management:")
        print("1. List containers")
        print("2. Create new container")
        print("3. Remove container")
        print("4. Check container status")
        print("5. Exit")
        
        choice = input("> ")
        
        match choice:
            case "1":
                users = manager.list_users()
                if users:
                    print("\nActive containers:")
                    for user in users:
                        # Get container status
                        status = subprocess.run(
                            f"docker inspect -f '{{{{.State.Status}}}}' taxi-{user}",
                            shell=True, capture_output=True, text=True
                        ).stdout.strip()
                        print(f"- taxi-{user} ({status})")
                else:
                    print("No containers found")
                    
            case "2":
                username = input("Enter username: ").strip()
                if not username:
                    print("Username cannot be empty")
                    continue
                    
                if manager.check_container_exists(username):
                    print(f"Container for {username} already exists")
                    continue
                
                ip = input("Enter IP address (format: 10.251.1.X): ").strip()
                mongo_password = input("Enter MongoDB password: ").strip()
                
                try:
                    print(f"\nSetting up container for {username}...")
                    # Create container
                    password = manager.add_user(username, ip, mongo_password)
                    print(f"\n✅ Container setup complete for {username}")
                    print(f"Password: {password}")
                    
                except Exception as e:
                    print(f"Error creating container: {e}")
                    
            case "3":
                username = input("Enter username to remove: ").strip()
                if not username:
                    print("Username cannot be empty")
                    continue
                    
                if not manager.check_container_exists(username):
                    print(f"No container found for {username}")
                    continue
                    
                confirm = input(f"Are you sure you want to remove container for {username}? (y/N): ").lower()
                if confirm == 'y':
                    try:
                        manager.remove_user(username)
                    except Exception as e:
                        print(f"Error removing container: {e}")
                        
            case "4":
                username = input("Enter username to check: ").strip()
                if not username:
                    print("Username cannot be empty")
                    continue
                
                if not manager.check_container_exists(username):
                    print(f"No container found for {username}")
                    continue
                
                # Get detailed container status
                cmd = f"docker inspect taxi-{username}"
                try:
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
                    status = subprocess.run(
                        f"docker inspect -f '{{{{.State.Status}}}}' taxi-{username}",
                        shell=True, capture_output=True, text=True
                    ).stdout.strip()
                    print(f"\nContainer taxi-{username}:")
                    print(f"Status: {status}")
                    print("Use 'docker logs taxi-{username}' for detailed logs")
                except subprocess.CalledProcessError as e:
                    print(f"Error checking container: {e}")
                    
            case "5":
                print("Exiting...")
                break
                
            case _:
                print("Invalid option")

if __name__ == "__main__":
    main()