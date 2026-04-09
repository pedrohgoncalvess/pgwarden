<div align="center">
  <h1>🛡️ PGWarden</h1>
  <p><strong>Advanced, centralized PostgreSQL monitoring and schema tracking for zero-downtime operations.</strong></p>
</div>

<br />

PGWarden is an open-source, robust solution designed to monitor multiple PostgreSQL databases simultaneously from a single pane of glass. It not only tracks performance metrics, locks, and active sessions in real-time, but also keeps a complete and versioned history of your schema (tables, columns, and indexes) changes over time.

---

## ✨ Features

- **Multi-Server Monitoring:** Connect and monitor several PostgreSQL servers and their databases dynamically.
- **Metric Collection:** Continuous polling of deep metrics like index usage, sequential scans, live/dead tuples, and vacuum stats.
- **Schema Versioning:** Keeps a historical audit trail of changes applied to your tables, columns, and indexes. 
- **Session & Lock Tracking:** See exactly what is hanging or taking too long with real-time session and lock capture.
- **FastAPI Backend:** A sleek, fully typed, asynchronous API to query metrics and register new targets.
- **Modern Web UI:** A beautiful frontend visualizing the raw time-series data and mapping out your database schema evolution.
- **Built on TimescaleDB:** Leverages TimescaleDB hypertables for highly efficient time-series metric storage and fast analytics queries.

## 🚀 Getting Started

PGWarden uses Docker and Docker Compose to make deployment seamless. 

### Prerequisites
- Docker
- Docker Compose

### Installation & Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/pedrohgoncalvess/pgwarden.git
   cd pgwarden
   ```

2. **Set up the Environment Variables**
   Create a `.env` file referencing the provided `.env.example`:
   ```bash
   cp .env.example .env
   ```
   *Make sure you define a strong `ENCRYPTION_KEY`. This key will be used by the API and the Collector to securely encrypt and decrypt the credentials of your monitored remote servers!*

3. **Start the Application**
   Run the full stack (TimescaleDB, Backend API, Collector, Migrations, and WebUI) using Docker Compose:
   ```bash
   docker compose up -d --build
   ```

4. **Access the Dashboards**
   - **Web UI:** Open your browser and navigate to `http://localhost:3000` (or the port defined in your setup) to access the main PGWarden observation dashboard.
   - **API Documentation:** You can explore the REST API via the built-in Swagger UI at `http://localhost:8080/docs`.

## ⚙️ Architecture

PGWarden is composed of several independent but heavily integrated services:

- **Database (TimescaleDB/PostgreSQL):** Stores both the application state (registered servers, auth, configuration) and the collected time-series metrics.
- **Collector:** A continuous, asynchronous python worker that spans out to all registered target databases, polls their states based on a configurable interval, and pushes the data back to the central database.
- **Migrations Service:** Automatically manages the central schema structure upon startup.
- **REST API:** A FastAPI service handling authentication, target registration, config loading, and data serving for the frontend.
- **Web UI:** The main dashboard enabling interaction with the collected metrics and schema history.

## 🤝 Contributing

We welcome contributions! Please feel free to submit a Pull Request, report Bugs, or suggest new Features. 

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is open-source and available under the standard MIT License.
