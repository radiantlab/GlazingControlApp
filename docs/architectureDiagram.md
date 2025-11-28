# High Level Architecture Diagram

```mermaid
graph TB
    subgraph "Frontend Layer"
        UI[React Web App<br/>AppHMI.tsx]
        API_CLIENT[API Client<br/>api.ts]
        COMPONENTS[Components<br/>RoomGrid, SidePanel, etc.]
    end

    subgraph "Backend API Layer"
        MAIN[main.py<br/>FastAPI Server]
        ROUTES[routes.py<br/>REST Endpoints]
        HEALTH["/health"]
        PANELS["/panels"]
        GROUPS["/groups"]
        COMMANDS["/commands/set-level"]
        AUDIT["/logs/audit"]
    end

    subgraph "Service Layer"
        SERVICE[ControlService<br/>service.py]
        CONFIG[config.py<br/>Environment Config]
    end

    subgraph "Backend Implementations"
        SIM[Simulator<br/>simulator.py<br/>Development Mode]
        ADAPTER[RealAdapter<br/>adapter.py<br/>Production Mode]
    end

    subgraph "Data Layer"
        STATE[state.py<br/>State Management]
        CONFIG_FILE[panels_config.json<br/>Structure Data]
        STATE_FILE[panels_state.json<br/>Runtime State]
        AUDIT_DB[audit.db<br/>SQLite Audit Log]
        MAPPING[window_mapping.json<br/>Panel → UUID Mapping]
    end

    subgraph "External Systems"
        HALIO_API[Halio API<br/>192.168.2.200:8084/api]
    end

    %% Frontend connections
    UI --> API_CLIENT
    UI --> COMPONENTS
    API_CLIENT --> ROUTES

    %% API Layer connections
    MAIN --> ROUTES
    ROUTES --> HEALTH
    ROUTES --> PANELS
    ROUTES --> GROUPS
    ROUTES --> COMMANDS
    ROUTES --> AUDIT

    %% Service Layer connections
    ROUTES --> SERVICE
    SERVICE --> CONFIG
    CONFIG --> |SVC_MODE=sim| SIM
    CONFIG --> |SVC_MODE=real| ADAPTER

    %% Data Layer connections
    SERVICE --> STATE
    SIM --> STATE
    STATE --> CONFIG_FILE
    STATE --> STATE_FILE
    STATE --> AUDIT_DB
    ADAPTER --> MAPPING

    %% External connections
    ADAPTER -->|X-API-Key Auth<br/>GET/POST Requests| HALIO_API

    %% Styling
    classDef frontend fill:#4A90E2,stroke:#2E5C8A,stroke-width:2px,color:#fff
    classDef api fill:#F5A623,stroke:#B8751A,stroke-width:2px,color:#fff
    classDef service fill:#50C878,stroke:#2E7D4E,stroke-width:2px,color:#fff
    classDef backend fill:#9B59B6,stroke:#6B3A7A,stroke-width:2px,color:#fff
    classDef data fill:#E74C3C,stroke:#A93226,stroke-width:2px,color:#fff
    classDef external fill:#34495E,stroke:#1A252F,stroke-width:2px,color:#fff

    class UI,API_CLIENT,COMPONENTS frontend
    class MAIN,ROUTES,HEALTH,PANELS,GROUPS,COMMANDS,AUDIT api
    class SERVICE,CONFIG service
    class SIM,ADAPTER backend
    class STATE,CONFIG_FILE,STATE_FILE,AUDIT_DB,MAPPING data
    class HALIO_API external
```

## Component Flow

### Request Flow (Setting Panel Level)
```
User Action → React Component → API Client → FastAPI Route 
→ ControlService → Backend (Simulator Or RealAdapter) 
→ State Management → Data Files
```

### Mode Switching
- **Sim Mode**: `SVC_MODE=sim` → Uses `Simulator` → Reads/Writes local JSON files
- **Real Mode**: `SVC_MODE=real` → Uses `RealAdapter` → Makes HTTP requests to Halio API

### Data Flow
- **Config Data** (panels_config.json): Panel/Group structure, names, relationships
- **State Data** (panels_state.json): Current tint levels, timestamps
- **Audit Log** (audit.db): SQLite database storing all control actions with actor, timestamp, result
- **Window Mapping** (window_mapping.json): Maps panel IDs (P01, P02) to Halio UUIDs

## Key Design Decisions

1. **Service Layer Abstraction**: `ControlService` provides a stable interface regardless of backend
2. **Mode Switching**: Zero code changes needed when switching between sim/real modes
3. **State Separation**: Config (structure) vs State (runtime values) separated for clarity and ease of repo use
4. **Error Handling**: All layers handle errors gracefully, returning empty arrays/None on failure
5. **Audit Trail**: All control actions logged with actor, timestamp, and result

