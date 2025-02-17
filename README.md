# Taxi Dev Center

VPN-based, containerized development workspace for Taxi members.

## About

Taxi Dev Center는 Taxi 팀원들을 위한 격리된 개발 환경을 제공하는 서비스입니다. Docker 컨테이너로 각 개발자에게 독립적인 환경을 제공하며, 컨테이너들은 공용 MongoDB와 통신합니다. 팀원들은 SPARCS VPN과 DNS를 통해 자신의 컨테이너에 도메인으로 접근할 수 있습니다.

각 개발자는 다음과 같은 환경을 제공받습니다:

- SSH 접근이 가능한 독립된 개발 컨테이너
- 개인 MongoDB 데이터베이스 계정 및 접근 권한
- 전용 DNS 레코드 (username.taxi.sparcs.org)
- 격리된 프론트엔드 (포트 3000) 및 백엔드 (포트 8080) 서비스
## Architecture

```mermaid
graph LR
    %% External Access Section
    subgraph External["External Access"]
        direction TB
        User["User<br>10.250.1.x/32"]
        VPN["WireGuard VPN<br>ssal.sparcs.org"]
    end

    subgraph DevServer["Development Server (taxi.dev.sparcs.org)"]
        direction TB
        subgraph Shared["Shared Services"]
            direction LR
            DNS["DNS Container<br>taxi-dns<br>10.251.1.2"]
            MongoDB["MongoDB Container<br>taxi-mongo-shared<br>10.251.1.3"]
        end

        subgraph Networks["Networks"]
            direction TB
            IPVLan["IPVLan Network (10.251.1.0/24)"]
            Bridge["Bridge Network (taxi-dc_shared-backend)"]
        end

        subgraph DevEnv["Development Environments"]
            direction TB
            subgraph Dev1["Development Container 1<br>taxi-user1.sparcs.org (10.251.1.X)"]
                direction TB
                SSH1[" SSH (22) "]
                Frontend1["Frontend (3000)<br>/home/ubuntu/taxi-front"]
                Backend1["Backend (8080)<br>/home/ubuntu/taxi-back"]
            end

            subgraph Dev2["Development Container 2<br>taxi-user2.sparcs.org (10.251.1.Y)"]
                direction TB
                SSH2[" SSH (22) "]
                Frontend2["Frontend (3000)<br>/home/ubuntu/taxi-front"]
                Backend2["Backend (8080)<br>/home/ubuntu/taxi-back"]
            end

            Dev3["..."]
        end
    end

    %% External Access Flow
    User -->|"Access via<br>WireGuard"| VPN
    VPN -->|"VPN Network<br>10.251.0.0/16"| DevServer

    %% DNS Resolution Flow
    User -.-|"1: Request<br>taxi-user1.sparcs.org"| DNS
    DNS -.-|"2: Resolve to<br>10.251.1.X"| Dev1

    %% Network Connections
    DNS --- IPVLan
    MongoDB --- IPVLan
    MongoDB --- Bridge

    Dev1 --- IPVLan
    Dev2 --- IPVLan

    %% Container Internal Connections
    SSH1 --- Frontend1
    SSH1 --- Backend1
    Backend1 ---|"MongoDB<br>Access"| Bridge

    SSH2 --- Frontend2
    SSH2 --- Backend2
    Backend2 ---|"MongoDB<br>Access"| Bridge

    classDef external fill:#e9a,stroke:#333,stroke-width:2px
    classDef server fill:#f9f,stroke:#333,stroke-width:4px
    classDef network fill:#ccf,stroke:#333,stroke-width:2px
    classDef container fill:#cfc,stroke:#333,stroke-width:2px
    classDef service fill:#fcc,stroke:#333,stroke-width:2px
    classDef flow stroke:#333,stroke-width:1px,stroke-dasharray: 5 5

    class User,VPN external
    class DevServer server
    class IPVLan,Bridge network
    class DNS,MongoDB,Dev1,Dev2,Dev3 container
    class SSH1,Frontend1,Backend1,SSH2,Frontend2,Backend2 service
```

## Directory Structure

```
taxi-dc/
├── taxi-dev-servers/           # Main development server component
│   ├── modules/               # Core functionality modules
│   │   ├── container_manager.py  # Docker container management
│   │   ├── dns_manager.py       # DNS configuration and management
│   │   └── mongo_manager.py     # MongoDB interaction and management
│   ├── scripts/              # Automation and setup scripts
│   │   └── entrypoint.sh      # Container initialization script
│   ├── users/                # Taxi Front/back repositories for all users
│   ├── docker-compose-files/ # Docker compose files for all users
│   ├── Dockerfile           # Main service Dockerfile
│   ├── Dockerfile.base      # Base image configuration
│   └── app.py              # Main application entry point
├── taxi-dns/                # DNS service component
│   ├── dns_backups/        # DNS configuration backups
│   ├── dnsmasq.conf        # Active DNS configuration
│   └── dnsmasq.conf.template # Template for DNS configuration
├── Configuration Files
│   ├── docker-compose.shared.yml      # Shared Docker configuration
│   ├── docker-compose.private.template.yaml  # Private Docker template
│   ├── requirements.txt     # Python dependencies
│   ├── .dockerignore       # Docker ignore rules
│   └── .gitignore          # Git ignore rules
└── Environment Files
    ├── .env                # Main environment variables
    ├── .env.back.development  # Backend dev environment
    ├── .env.back.test     # Backend test environment
    └── .env.front         # Frontend environment
```

## Project Setup

1. Create environment files from templates:
   ```bash
   cp .env.template .env
   cp .env.back.development.template .env.back.development
   cp .env.back.test.template .env.back.test
   cp .env.front.template .env.front
   ```

2. Set up Python virtual environment:
   ```bash
   python -m venv taxi-env
   source taxi-env/bin/activate
   pip install -r requirements.txt
   ```

3. Start shared services:
   ```bash
   docker compose -f docker-compose.shared.yml up -d
   ```

## Running Taxi-DC

1. Activate virtual environment:
   ```bash
   source taxi-env/bin/activate
   ```

2. Run the management application:
   ```bash
   python taxi-dev-servers/app.py
   ```

3. Available commands:
   - List all entries (containers, DNS, MongoDB)
   - Create new development environment
   - Edit user configurations
   - Remove development environment

## Flow
```mermaid
sequenceDiagram
    participant User
    participant Taxi Dev Center
    participant DNS Manager
    participant MongoDB Manager
    participant Container Manager

    Note over User,Container Manager: Create User Flow
    User->>Taxi Dev Center: Create new user (username, IP)
    Taxi Dev Center->>DNS Manager: Create DNS entry
    DNS Manager-->>Taxi Dev Center: DNS entry created
    Taxi Dev Center->>MongoDB Manager: Create MongoDB user
    MongoDB Manager-->>Taxi Dev Center: MongoDB credentials
    Taxi Dev Center->>Container Manager: Create container
    Container Manager-->>Taxi Dev Center: SSH credentials
    Taxi Dev Center-->>User: All credentials

    Note over User,Container Manager: Edit User Flow
    User->>Taxi Dev Center: Edit user details
    alt Edit Username
        Taxi Dev Center->>MongoDB Manager: Update username
        MongoDB Manager-->>Taxi Dev Center: New credentials
        Taxi Dev Center->>DNS Manager: Update DNS
        DNS Manager-->>Taxi Dev Center: Success
        Taxi Dev Center->>Container Manager: Update container
        Container Manager-->>Taxi Dev Center: Success
    else Edit IP Only
        Taxi Dev Center->>DNS Manager: Update IP
        DNS Manager-->>Taxi Dev Center: Success
        Taxi Dev Center->>Container Manager: Update container
        Container Manager-->>Taxi Dev Center: Success
    end
    Taxi Dev Center-->>User: Update complete

    Note over User,Container Manager: Remove User Flow
    User->>Taxi Dev Center: Remove user
    Taxi Dev Center->>Container Manager: Remove container
    Container Manager-->>Taxi Dev Center: Success
    Taxi Dev Center->>DNS Manager: Remove DNS entry
    DNS Manager-->>Taxi Dev Center: Success
    Taxi Dev Center->>MongoDB Manager: Remove MongoDB user
    MongoDB Manager-->>Taxi Dev Center: Success
    Taxi Dev Center-->>User: User removed

    Note over User,Container Manager: List Users Flow
    User->>Taxi Dev Center: List all users
    Taxi Dev Center->>DNS Manager: Get DNS entries
    DNS Manager-->>Taxi Dev Center: DNS entries
    Taxi Dev Center->>MongoDB Manager: Get MongoDB users
    MongoDB Manager-->>Taxi Dev Center: MongoDB users
    Taxi Dev Center->>Container Manager: Get container status
    Container Manager-->>Taxi Dev Center: Container status
    Taxi Dev Center-->>User: Combined table
```
