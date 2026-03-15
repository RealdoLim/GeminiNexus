# RahmahOps — Ramadan Food Aid Coordination Swarm

RahmahOps is an agentic operations dashboard for coordinating Ramadan food-aid distribution. It helps a coordinator turn a mission brief into a live distribution plan, assign volunteers to routes, enrich assignments with travel ETA and distance, monitor urgency before Maghrib, and recover when disruptions happen.

During Ramadan, many community food-aid drives are still coordinated through WhatsApp, spreadsheets, and phone calls. One volunteer cancellation or one time-critical bottleneck can delay iftar support for families. RahmahOps is built to make that process more observable, recoverable, and safer.

---

## Youtube Demo Video Link
https://youtu.be/ItwNL29PFmY

## Project Overview

RahmahOps is a **Track C: Operations Hub** project focused on **process automation, orchestration, and API interactions**.

It uses:
- **Google ADK + Gemini** for orchestration and recovery reasoning
- **MCP tools** for external integrations
- a **web dashboard** for mission control
- **structured operational logs** as visible “thinking” traces
- **guardrails** for mission validation, privacy, and safe fallback behavior

### What RahmahOps does
A coordinator loads a structured mission brief containing:
- food package batches
- distribution points
- volunteers
- recipient clusters
- remaining time before Maghrib

RahmahOps then:
- validates the mission brief
- builds the initial route plan
- assigns volunteers
- enriches assignments with route ETA and distance
- monitors operational state
- recovers from disruptions

### Featured recovery scenarios
- **Volunteer Cancellation** — reassigns affected load to the best available volunteer(s)
- **Maghrib Critical / Triage Mode** — reschedules lower-priority clusters when time becomes critical before iftar

### Agent Profiles

orchestrator_agent

The central coordinator of RahmahOps. It normalizes the mission brief, triggers validation, launches the operational workflow, and coordinates downstream agents. It also logs final summaries and coordinates recovery workflows.

guard_agent

The mission-validation and safety gate. It checks whether the mission brief is structurally valid, whether package and capacity constraints are sane, and whether the brief contains unsafe, discriminatory, or suspicious instructions.

routing_agent

Builds the initial route plan across distribution points based on package availability, point capacity, and recipient load. It also works with the Google Routes MCP integration to enrich volunteer assignments with travel ETA and distance.

volunteer_agent

Assigns volunteers to planned routes using availability, capacity, and location heuristics. It stores live assignment state and is central to recovery during volunteer cancellation incidents.

recipient_agent

Tracks recipient clusters per distribution point. During Maghrib-critical triage, it marks lower-priority or distant clusters as rescheduled and updates the operational plan safely.

recovery_agent

Handles mission disruptions. In the current build, it supports:

volunteer cancellation recovery

Maghrib-critical triage mode

It combines ADK orchestration with deterministic fallback logic to keep the system reliable during the demo.

comms_agent

Drafts operational notifications for the coordinator and affected parties. These are shown in the dashboard notification feed and are part of the recovery story.

### MCP Tools
prayer_time_mcp.py

Provides Maghrib prayer-time data using the AlAdhan API.

Purpose

fetch Maghrib time for the mission city

estimate urgency before iftar

support the Maghrib-critical recovery workflow

google_routes_mcp.py

Provides route matrix data using the Google Routes API.

Purpose

compute ETA and distance between volunteer origins and distribution points

enrich volunteer assignments with real route information

strengthen route visibility in the dashboard

## Tech Stack

Backend: Python, FastAPI, Uvicorn

Agent Framework: Google ADK

Model: Gemini

Frontend: HTML, CSS, JavaScript

State Modeling: Pydantic

MCP Integrations:

AlAdhan Prayer Time API

Google Routes API

Environment Config: .env

### Setup Instructions

1. Clone the repository
git clone <your-repo-url>
cd <your-repo-folder>

2. Create and activate a virtual environment

Windows (PowerShell)

python -m venv .venv
.venv\Scripts\Activate.ps1


If activation is blocked:

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1

3. Install dependencies
pip install -r requirements.txt

4. Configure environment variables

Create a .env file based on .env.example.

Example:

GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=your_gemini_api_key_here
GOOGLE_MAPS_API_KEY=your_google_maps_key_here

5. Run the app
python -m uvicorn main:app --reload

6. Open the dashboard
http://127.0.0.1:8000

## Future updates
- Create a UI interface for the user to input a json/txt file containing mission details

- Apply more problems that need recovery such as point closure or food safety

- Deploy web-app 

## System Architecture Diagram (A2A Flow)

```mermaid
flowchart TD
    A[Coordinator Mission Brief / JSON Input] --> B[guard_agent<br/>Mission Validation & Policy Checks]

    B -->|Passed| C[orchestrator_agent<br/>Central Control Plane]
    B -->|Blocked| BX[Stop Execution<br/>Validation / Safety Failure]

    C --> D[routing_agent<br/>Build Distribution Route Plan]
    D --> D1[Google Routes MCP<br/>ETA + Distance Enrichment]

    C --> E[volunteer_agent<br/>Assign Volunteers to Routes]
    C --> F[recipient_agent<br/>Track Recipient Clusters / Rescheduling]
    C --> G[comms_agent<br/>Draft Coordinator / Recipient Notifications]

    C -->|Incident: Volunteer Cancellation| H[recovery_agent<br/>Recovery Orchestration]
    C -->|Incident: Maghrib Critical| H

    H --> H1[Prayer Time MCP<br/>Maghrib Urgency Signal]
    H --> E
    H --> F
    H --> G

    D1 --> D
    H1 --> H

    H -->|Fallback on tool failure| HF[Deterministic Safe Recovery]

    You can input this to mermaid or go to the diagram file in this folder

