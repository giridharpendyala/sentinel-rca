# Multi-Agent AI for Observability & Incident Investigation

## 1. Problem Statement

Modern enterprise applications generate large amounts of telemetry through **metrics, logs and distributed traces**. When an application experiences increased latency, errors, or service degradation, engineers typically investigate multiple dashboards and telemetry sources to identify the root cause.

For example:

> **Checkout Service p95 latency increased from 400 ms to 4 seconds and the error rate increased significantly. Identify the probable root cause.**

An engineer may need to:

* Examine application and infrastructure metrics
* Analyze distributed traces
* Search application logs
* Check recent deployments or configuration changes
* Correlate evidence across these sources

The objective of this capstone is to develop a **multi-agent AI system that automatically performs this investigation**, correlates telemetry, identifies the probable root cause, and provides supporting evidence.

The project should additionally demonstrate the complete **AgentOps lifecycle**, including agent tracing, evaluation, monitoring and regression testing.

---

# 2. Proposed Multi-Agent Solution

Use **LangGraph** to orchestrate a small set of specialized agents.

```text
                 Incident / Alert
                       │
                       ▼
              ┌─────────────────┐
              │ Supervisor Agent│
              └────────┬────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
      Metrics       Traces        Logs
       Agent         Agent         Agent
          │            │            │
          └────────────┼────────────┘
                       ▼
                 Change Agent
                       │
                       ▼
                    RCA Agent
                       │
                       ▼
              Incident Summary
```

### Supervisor Agent

Understands the incident and decides how the investigation should proceed.

For example:

```text
1. Analyze Checkout metrics.
2. Find slow traces.
3. Investigate the affected service logs.
4. Check recent changes.
5. Correlate evidence and determine RCA.
```

The investigation does not have to follow exactly the same sequence every time. LangGraph maintains the investigation state and allows the Supervisor to decide the next action based on previous findings.

### Metrics Agent

Queries Prometheus or simulated metrics and investigates:

* latency
* request rate
* error rate
* CPU/memory
* connection pools

### Trace Agent

Analyzes OpenTelemetry traces to determine where latency or errors originate.

### Log Agent

Searches logs for errors associated with the affected service and time window.

### Change Agent

Checks recent application deployments or configuration changes.

### RCA Agent

Combines evidence collected by the other agents and produces the probable root cause, confidence and recommended next steps.

---

# 3. Example Investigation

Assume the following alert is received:

> **Checkout API latency increased from 400 ms to 4.5 seconds starting at 14:32.**

The Supervisor starts an investigation.

### Step 1 — Metrics

The Metrics Agent discovers:

```text
Checkout latency: HIGH
Checkout errors: HIGH
CPU: NORMAL
Memory: NORMAL

Payment Service:
DB connections = 50/50
```

It identifies DB connection saturation as suspicious.

### Step 2 — Traces

The Trace Agent examines slow transactions:

```text
Checkout API
   │
   ├── Cart Service       50 ms
   ├── Pricing Service    80 ms
   │
   └── Payment Service  4100 ms
            │
            └── Database 3900 ms
```

The investigation is therefore narrowed to:

```text
Payment Service → Database
```

### Step 3 — Logs

The Supervisor asks the Log Agent to investigate Payment Service around the incident period.

The logs contain:

```text
WARN  Timeout waiting for database connection

ERROR Unable to acquire JDBC connection
```

This supports the connection-pool hypothesis.

### Step 4 — Recent Changes

The Change Agent finds:

```text
14:27

payment-service v4.18.2 deployed

DB_POOL_SIZE:
100 → 50
```

The incident started five minutes later.

### Step 5 — RCA

The RCA Agent correlates the evidence:

```text
Probable Root Cause:

Payment Service database connection pool
exhaustion following deployment v4.18.2.

Evidence:

1. Payment Service accounts for most request latency.
2. DB connection pool reached 50/50.
3. Logs contain connection acquisition timeouts.
4. Deployment occurred five minutes before the incident.
5. DB_POOL_SIZE changed from 100 to 50.

Confidence: High

Recommended Action:

Review and restore the previous connection-pool
configuration after SRE approval.
```

The important requirement is that the RCA must be **grounded in actual telemetry retrieved by the agents**, rather than generated only from LLM reasoning.

---

# 4. Suggested Technology Stack

Keep the implementation relatively small.

| Area                      | Suggested Technology                   |
| ------------------------- | -------------------------------------- |
| Multi-agent orchestration | LangGraph                              |
| LLM integration           | LangChain / model SDK                  |
| Metrics                   | Prometheus                             |
| Logs                      | Loki                                   |
| Traces                    | OpenTelemetry + Tempo/Jaeger           |
| Visualization             | Grafana                                |
| Agent tracing             | LangSmith **or** Langfuse              |
| Evaluation                | LangSmith/Langfuse + custom evaluators |
| Knowledge/RAG             | Optional pgvector                      |
| Application               | Python                                 |

The telemetry can be generated using a small synthetic microservices application instead of integrating with actual enterprise production systems.

---

# 5. AgentOps

AgentOps is an important part of the capstone.

Every incident investigation should itself be observable.

Using **LangSmith or Langfuse**, capture:

```text
Incident
   │
Supervisor
   │
   ├── Metrics Agent
   │      └── Prometheus query
   │
   ├── Trace Agent
   │      └── Trace query
   │
   ├── Log Agent
   │      └── Log query
   │
   ├── Change Agent
   │
   └── RCA Agent
```

For every investigation record:

* Agent calls
* LLM calls
* Tool calls
* Agent handoffs
* Inputs and outputs
* Tokens
* Latency
* Errors/retries
* Cost
* Final RCA
* Evaluation results

This gives the project two interesting observability levels:

```text
Application
     │
     │ Metrics / Logs / Traces
     ▼
AI Agents
     │
     │ Agent traces / LLM calls / Tool calls
     ▼
AgentOps
```

The **AI system uses observability to investigate applications, while AgentOps provides observability of the AI system itself.**

---

# 6. Evaluation

Create approximately **10 known incident scenarios**.

For example:

| Incident | Ground Truth             |
| -------- | ------------------------ |
| INC-01   | DB connection exhaustion |
| INC-02   | High CPU                 |
| INC-03   | Memory leak              |
| INC-04   | Bad deployment           |
| INC-05   | Downstream API slowdown  |
| INC-06   | Database lock            |
| INC-07   | Kubernetes OOM           |
| INC-08   | Traffic spike            |
| INC-09   | Configuration error      |
| INC-10   | Application exception    |

For each incident, store the expected root cause and important supporting evidence.

Then evaluate:

**RCA Accuracy**

Did the system identify the correct root cause?

**Evidence Grounding**

Is the RCA supported by telemetry?

**Tool Selection**

Did agents query the appropriate telemetry sources?

**Investigation Path**

Did the agents follow a reasonable investigation sequence?

**Hallucination**

Did the system claim evidence that wasn't present?

**Efficiency**

How many LLM calls, tool calls, tokens and seconds were required?

---

# 7. AgentOps Regression Pipeline

The evaluation dataset can also be used as a regression suite.

```text
Agent / Prompt Change
        │
        ▼
Run 10 Test Incidents
        │
        ▼
Evaluate
        │
 ┌──────┼─────────┐
 ▼      ▼         ▼
RCA   Grounding  Cost
Accuracy
        │
        ▼
 Compare with Previous Version
        │
        ▼
   Release / Improve
```

For example:

```text
Agent Version 1

RCA accuracy       70%
Grounding          82%
Avg tool calls     21
Avg latency        28 sec


Agent Version 2

RCA accuracy       90%
Grounding          94%
Avg tool calls     14
Avg latency        19 sec
```

This demonstrates that AgentOps is not simply tracing. It is being used to **measure and improve the agent system over time**.

---

# 8. Enterprise Considerations

A few enterprise requirements should still be demonstrated without making the project overly complicated.

Agents should have **read-only access** to telemetry systems.

Sensitive log information should be masked before being sent to the LLM.

Production actions such as restarting services, changing configurations or rolling back deployments should require **human approval**.

All agent and tool activity should be auditable through AgentOps traces.

---

# 9. Expected Deliverables

The capstone should deliver:

1. Working LangGraph multi-agent application
2. Metrics, logs and trace integration
3. Example microservices incident environment
4. 10 reproducible incident scenarios
5. LangSmith or Langfuse AgentOps integration
6. Automated evaluation framework
7. Agent tracing and evaluation dashboard
8. Demonstration of one complete incident investigation
9. Architecture and design documentation

## End-to-End Demonstration

The final demonstration should show one continuous workflow:

```text
Application Problem
        ↓
Alert / User Question
        ↓
Supervisor Agent
        ↓
Metrics / Logs / Traces
        ↓
Evidence Collection
        ↓
Recent Change Analysis
        ↓
RCA
        ↓
Recommended Action
        ↓
AgentOps Trace
        ↓
Evaluation
```

The capstone therefore demonstrates the complete lifecycle:

**Incident → Agentic Investigation → Evidence → RCA → AgentOps → Evaluation → Improvement**

The core goal is to show that a multi-agent system can perform a realistic observability investigation while remaining **traceable, measurable and evaluable**.
