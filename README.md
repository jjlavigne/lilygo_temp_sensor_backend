# Commercial Fleet Telemetry Pipeline

## Project Overview
An end-to-end, event-driven IoT pipeline designed to monitor commercial fleet produce delivery temperatures in real-time. The system routes edge-device telemetry through a decoupled message broker and securely logs it into a persistent relational database for future analysis.

Currently prototyped with software-based mock edge nodes, with architecture designed for immediate swap to physical LilyGO T-SIM7000G industrial hardware.

## Architecture & Tech Stack
* **Edge Hardware:** LilyGO T-SIM7000G (Currently simulated via Python)
* **Message Broker:** Eclipse Mosquitto (MQTT)
* **Database Engine:** PostgreSQL 15
* **Backend Logic:** Python 3.12 (`paho-mqtt`, `psycopg2-binary`)
* **Infrastructure:** Docker Desktop / Docker Compose running on WSL 2 (Nested Virtualization)

## System Components

### 1. Docker Infrastructure (`docker-compose.yml`)
The foundational infrastructure runs in isolated Linux containers to ensure absolute production parity when eventually deployed to the cloud. 
* Uses a custom virtual network to allow the broker and database to communicate.
* Implements a local Docker volume (`pgdata`) mapped to the host machine to ensure PostgreSQL data persists even if the containers are destroyed.

### 2. The MQTT Broker (`mosquitto.conf`)
Acts as the central routing hub. Edge devices publish JSON payloads to the `fleet/telemetry` topic, keeping the edge hardware completely decoupled from the backend database logic.

### 3. Backend Ingestion Service (`backend/ingestion.py`)
A persistent Python service that bridges the broker and the database. 
* Connects to PostgreSQL and verifies/initializes the relational `telemetry` table.
* Subscribes to the Mosquitto broker.
* Safely unpacks incoming JSON payloads and executes parameterized SQL inserts to permanently store the timestamped temperature, GPS, and battery data.

### 4. Edge Publisher (`mock-device/mock_publisher.py`)
A testing utility that generates realistic commercial fleet data and publishes it to the broker at fixed intervals to validate the pipeline before hardware deployment.

## Boot Sequence
To bring the pipeline online from a cold start:

1. **Start Infrastructure:** Open Docker Desktop and start the `fleet-telemetry` stack (or run `docker compose start` in the terminal).
2. **Start Listener:** Open terminal, navigate to `/backend`, and run `python ingestion.py`.
3. **Start Edge Devices:** Turn on physical LilyGO hardware, or run `python mock_publisher.py` in a separate terminal.