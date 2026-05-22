# Shift Scheduling Optimization System

A robust, enterprise-grade Full-Stack Shift Scheduling Application that automates complex workforce management. The system utilizes mathematical constraint programming to solve scheduling puzzles, ensuring absolute compliance with operational constraints while maximizing employee preference and fairness.

The core optimization engine is powered by **Google OR-Tools (CP-SAT Solver)**, wrapped in a **Flask** backend (deployed on Render), with a modern, responsive **React (Tailwind CSS)** frontend (deployed on Vercel).

---

## Key Features

- **Automated Mathematical Scheduling:** Replaces manual overhead by calculating optimal shift rosters in seconds based on a Constraint Programming model.
- **Dynamic Employee & Rank Management:** Supports a hierarchical classification system (Rank 1: Junior Researcher, Rank 2: Senior Researcher, Rank 3: Team Lead) with dedicated operational capabilities.
- **Strict Compliance Enforcement:** Hardcoded operational rules guarantee required rest periods, shift counts, and structural command constraints.
- **Smart Historical Continuity:** Integrates a historical input mechanism to account for prior shift states, preventing back-to-back shift assignments between consecutive cycles.
- **Flexible Optimization Strategies:** Toggle between *Fairness* (distributing load evenly) and *Balance* (minimizing unnecessary over-staffing) to align with different operational goals.
- **Excel Data Integration:** Import employee rosters directly using pre-formatted Excel templates and export finalized rosters seamlessly via SheetJS.

---

## System Architecture & Constraints Model

The backend maps the scheduling matrix into a Finite Domain Constraint Programming problem.

### Hard Constraints (Strict Compliance)
1. **Shift Demand:** Every active shift must be filled by the exact number of required employees.
2. **Team Lead Presence (Rank 3):** Shifts flagged as leadership-dependent must contain at least one Team Lead.
3. **Senior Presence (Rank >= 2):** Critical shifts must contain at least one experienced researcher (Senior or Team Lead) to prevent purely junior configurations.
4. **No Overlaps:** An employee cannot be assigned to overlapping or concurrent shifts on the same calendar day.
5. **Night Shift Rest Loop:** Any employee assigned to a night shift is automatically blocked from morning shifts the following day.
6. **Weekly Quotas:** Tracks and locks bounds on minimum and maximum weekly shifts per employee.

### Soft Constraints (Objective Optimization Metrics)
- **Excess Experience Penalty:** Penalizes grouping multiple high-ranking employees in non-critical shifts to conserve workforce energy.
- **Senior Utilization:** Balances the operational load across available senior personnel.

---

## Tech Stack

- **Frontend:** React.js, Tailwind CSS, SheetJS (XLSX parsing & generation)
- **Backend:** Python, Flask, Gunicorn, Flask-CORS
- **Optimization Engine:** Google OR-Tools (CP-SAT Solver)