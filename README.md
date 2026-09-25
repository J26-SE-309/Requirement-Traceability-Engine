# Requirement Traceability Engine

> A microservice of **Synapse**, an AI-assisted agile project platform built by research group **J26-SE-309**.

![Status](https://img.shields.io/badge/status-initial%20setup-orange)

## Overview

This service traces requirements across the project lifecycle, linking them to related artifacts so teams can see how each requirement is covered and what a change affects.

Scope, methodology, datasets and models will be documented here as the research progresses.

## Repository Layout (planned)

```
Requirement-Traceability-Engine/
├── backend/     # Service API consumed by Synapse-Web
└── ml-engine/   # Model training, evaluation and inference
```

## Getting Started

```bash
git clone https://github.com/J26-SE-309/Requirement-Traceability-Engine.git
cd Requirement-Traceability-Engine
```

Setup and run instructions will be added once the backend and ML engine are scaffolded.

## Synapse Platform Services

| Service | Repository | Type |
|---|---|---|
| Synapse Web | [Synapse-Web](https://github.com/J26-SE-309/Synapse-Web) | Frontend |
| Effort Estimation and Sprint Risk Predictor | [Effort-Estimation-and-Sprint-Risk-Predictor](https://github.com/J26-SE-309/Effort-Estimation-and-Sprint-Risk-Predictor) | Backend + ML engine |
| Requirement Quality and Ambiguity Analyzer | [Requirement-Quality-and-Ambiguity-Analyzer](https://github.com/J26-SE-309/Requirement-Quality-and-Ambiguity-Analyzer) | Backend + ML engine |
| **Requirement Traceability Engine** | [Requirement-Traceability-Engine](https://github.com/J26-SE-309/Requirement-Traceability-Engine) | Backend + ML engine |
| User Story Refinement and Acceptance Criteria Generator | [User-Story-Refinement-Acceptance-Criteria-Generator](https://github.com/J26-SE-309/User-Story-Refinement-Acceptance-Criteria-Generator) | Backend + ML engine |

## Project Lead

- [@Nikeshala22](https://github.com/Nikeshala22)
