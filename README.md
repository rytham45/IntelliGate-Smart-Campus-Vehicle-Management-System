IntelliGate AI: Smart Campus Vehicle Management System

Project Overview

IntelliGate AI is a computer-vision-based access control system that digitizes vehicle entry to enhance institutional security and campus automation. It replaces inefficient manual parking verification with a fast, fail-proof digital pipeline.

The Core Problem

 * Security Bypasses: Guards frequently skip tedious manual checks during peak traffic, compromising campus safety.
 * Fraud & Duplication: Physical parking stickers are easily duplicated, faked, or shared among unauthorized users.
 * High Error Rates: Human visual verification is highly prone to mistakes under pressure.

The Solution & Architecture

 * Mobile Capture (Kotlin): A lightweight Android app captures, compresses, and transmits vehicle images via REST API.
 * Machine Learning Engine (Python): A locally hosted model rapidly detects license plates and extracts text without relying on third-party APIs.
 * Backend Verification (Django/MongoDB): Queries the extracted plate against the active registry, strictly enforcing issuance and expiration dates.
 * Real-Time Feedback: Returns an instant JSON response (e.g., {"status": "AUTHORIZED", "plate": "PB02AB1234"}) to the mobile UI for immediate, color-coded confirmation.

Measurable Impact & Future Scope

 * Frictionless Entry & Zero Fraud: Reduces gate processing to seconds, clears bottlenecks, and eliminates sticker duplication by tying access directly to the vehicle's plate.
 * Automated Audit Trails: Replaces manual ledgers with a fully searchable, timestamped digital log of all campus traffic.
 * Future Scalability: Lays the foundation for a web portal where students can renew passes entirely online, eliminating administrative queues.