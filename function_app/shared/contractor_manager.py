"""
AI Contractor Manager — Clone Visualizer Layer 1.

Manages named AI Contractor pools for each agent stage.
Implements first-fill job assignment, spawn/terminate lifecycle,
and state snapshots for the real-time dashboard.

This module has zero dependency on Azure Durable Functions and can
be tested standalone with a simple Python script.
"""

import logging
import threading
import time as _time
from collections import deque
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# =============================================================================
# Progress Simulation Config
# =============================================================================

ESTIMATED_STAGE_DURATION_SECONDS = {
    "classifier": 15,       # Agent1 typically takes ~15s
    "adjudicator": 10,      # Agent2 typically takes ~10s
    "email_composer": 8,    # Agent3 typically takes ~8s
}

PROGRESS_TICK_INTERVAL = 0.5  # seconds between progress updates
PROGRESS_CAP = 95             # never exceed this from simulation


# =============================================================================
# Event Log
# =============================================================================

class ContractorEvent:
    """A single event in the contractor event log."""

    __slots__ = ("timestamp", "agent_id", "event_type", "contractor_name",
                 "claim_id", "message")

    def __init__(self, agent_id: str, event_type: str, contractor_name: str,
                 claim_id: Optional[str], message: str):
        self.timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.agent_id = agent_id
        self.event_type = event_type
        self.contractor_name = contractor_name
        self.claim_id = claim_id
        self.message = message

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "agent": self.agent_id,
            "type": self.event_type,
            "contractor": self.contractor_name,
            "claim_id": self.claim_id,
            "message": self.message,
        }


class ContractorPool:
    """Manages the contractor workforce for a single agent stage.

    Implements:
    - First-fill job assignment (fill earliest contractor first)
    - Spawn on demand (when all contractors are full)
    - Scale-down (terminate empty contractors in reverse spawn order)
    - Thread-safe state management
    """

    def __init__(
        self,
        agent_id: str,
        display_name: str,
        capacity: int,
        max_contractors: int,
        contractor_defs: list[dict],
        event_log: Optional[deque] = None,
        event_lock: Optional[threading.Lock] = None,
    ):
        """
        Args:
            agent_id: Stage identifier ("classifier", "adjudicator", "email_composer")
            display_name: Human-readable name for dashboard
            capacity: Max concurrent jobs per contractor (N)
            max_contractors: Upper bound on contractor count
            contractor_defs: List of {"name": "Alice", "color": "#2dd4a8"} definitions
            event_log: Shared event log deque (from ContractorManager)
            event_lock: Shared lock for event log
        """
        self.agent_id = agent_id
        self.display_name = display_name
        self.capacity = capacity
        self.max_contractors = max_contractors
        self.contractor_defs = contractor_defs
        self.active_contractors: list[dict] = []
        self.pending_queue: list[str] = []
        self.total_completed: int = 0
        self._lock = threading.Lock()
        self._event_log = event_log
        self._event_lock = event_lock

        # Always spawn the primary contractor (never terminated)
        self._spawn_contractor(is_primary=True)

    # =========================================================================
    # Public API
    # =========================================================================

    def assign_job(self, claim_id: str) -> Optional[str]:
        """Assign a job using first-fill logic.

        Walks contractors in spawn order, assigns to the first with a free slot.
        If all are full, spawns the next contractor (if under max).
        If at max, queues the job.

        Args:
            claim_id: The claim to assign

        Returns:
            Contractor name if assigned, None if queued
        """
        with self._lock:
            return self._assign_job_unlocked(claim_id)

    def complete_job(self, claim_id: str) -> bool:
        """Mark a job as complete, assign pending, and run scale-down.

        Args:
            claim_id: The claim that completed

        Returns:
            True if the job was found and removed, False otherwise
        """
        with self._lock:
            found = False
            for contractor in self.active_contractors:
                for job in contractor["active_jobs"]:
                    if job["claim_id"] == claim_id:
                        contractor["active_jobs"].remove(job)
                        contractor["jobs_completed"] += 1
                        self.total_completed += 1
                        found = True
                        logger.info(
                            f"[{self.agent_id}] Job {claim_id} completed by "
                            f"{contractor['name']} ({len(contractor['active_jobs'])}/{self.capacity})"
                        )
                        self._record_event(
                            "job_completed", contractor["name"], claim_id,
                            f"{claim_id} completed by {contractor['name']} at {self.display_name}"
                        )
                        break
                if found:
                    break

            if not found:
                logger.warning(f"[{self.agent_id}] Job {claim_id} not found in any contractor")
                return False

            # Assign any pending jobs to freed slots
            self._assign_pending_unlocked()

            # Scale-down empty non-primary contractors
            self._scale_down_unlocked()

            return True

    def update_progress(self, claim_id: str, progress_pct: int):
        """Update the progress percentage of an active job.

        Args:
            claim_id: The claim to update
            progress_pct: New progress value (0-100)
        """
        with self._lock:
            for contractor in self.active_contractors:
                for job in contractor["active_jobs"]:
                    if job["claim_id"] == claim_id:
                        job["progress_pct"] = min(100, max(0, progress_pct))
                        return

    def get_state(self) -> dict:
        """Return a full state snapshot for dashboard rendering.

        Returns:
            Dictionary matching ContractorPoolState schema
        """
        with self._lock:
            contractors_state = []
            for c in self.active_contractors:
                slots_used = len(c["active_jobs"])
                if slots_used >= self.capacity:
                    status = "full"
                elif slots_used == 0:
                    status = "idle"
                else:
                    status = "available"

                contractors_state.append({
                    "name": c["name"],
                    "color": c["color"],
                    "capacity": self.capacity,
                    "active_jobs": [
                        {
                            "claim_id": j["claim_id"],
                            "progress_pct": j["progress_pct"],
                            "started_at": j["started_at"],
                            "status": j["status"],
                        }
                        for j in c["active_jobs"]
                    ],
                    "slots_used": slots_used,
                    "jobs_completed": c["jobs_completed"],
                    "status": status,
                    "is_primary": c["is_primary"],
                })

            return {
                "agent_id": self.agent_id,
                "display_name": self.display_name,
                "capacity_per_contractor": self.capacity,
                "max_contractors": self.max_contractors,
                "pending_queue": list(self.pending_queue),
                "pending_count": len(self.pending_queue),
                "active_contractors": contractors_state,
                "contractor_count": len(self.active_contractors),
                "total_jobs_in_flight": sum(
                    len(c["active_jobs"]) for c in self.active_contractors
                ),
                "total_completed": self.total_completed,
            }

    # =========================================================================
    # Internal — must be called under self._lock
    # =========================================================================

    def _assign_job_unlocked(self, claim_id: str) -> Optional[str]:
        """First-fill assignment (no lock — caller must hold lock)."""
        # Try existing contractors in spawn order
        for contractor in self.active_contractors:
            if len(contractor["active_jobs"]) < self.capacity:
                self._add_job_to_contractor(contractor, claim_id)
                return contractor["name"]

        # All full — try to spawn
        if len(self.active_contractors) < self.max_contractors:
            new_contractor = self._spawn_contractor()
            self._add_job_to_contractor(new_contractor, claim_id)
            return new_contractor["name"]

        # Max reached — queue
        self.pending_queue.append(claim_id)
        logger.info(
            f"[{self.agent_id}] Job {claim_id} queued (all {self.max_contractors} "
            f"contractors full, pending={len(self.pending_queue)})"
        )
        return None

    def _assign_pending_unlocked(self):
        """Try to assign pending jobs to available slots (no lock)."""
        while self.pending_queue:
            assigned = False

            # First-fill across existing contractors
            for contractor in self.active_contractors:
                if len(contractor["active_jobs"]) < self.capacity and self.pending_queue:
                    claim_id = self.pending_queue.pop(0)
                    self._add_job_to_contractor(contractor, claim_id)
                    assigned = True
                    break

            if not assigned:
                # Try to spawn
                if len(self.active_contractors) < self.max_contractors:
                    new_contractor = self._spawn_contractor()
                    claim_id = self.pending_queue.pop(0)
                    self._add_job_to_contractor(new_contractor, claim_id)
                else:
                    break  # Truly at max capacity

    def _scale_down_unlocked(self):
        """Terminate empty non-primary contractors in reverse spawn order (no lock)."""
        # Walk in reverse so we terminate last-spawned first
        to_remove = []
        for contractor in reversed(self.active_contractors):
            if not contractor["is_primary"] and len(contractor["active_jobs"]) == 0:
                to_remove.append(contractor)
                logger.info(
                    f"[{self.agent_id}] Contractor {contractor['name']} terminated "
                    f"(empty, not primary)"
                )
                self._record_event(
                    "terminate", contractor["name"], None,
                    f"{contractor['name']} terminated at {self.display_name} (empty, not primary)"
                )

        for contractor in to_remove:
            self.active_contractors.remove(contractor)

    def _spawn_contractor(self, is_primary: bool = False) -> dict:
        """Spawn the next contractor from the definition list (no lock)."""
        idx = len(self.active_contractors)
        if idx >= len(self.contractor_defs):
            raise RuntimeError(
                f"[{self.agent_id}] Cannot spawn contractor #{idx+1}: "
                f"only {len(self.contractor_defs)} definitions available"
            )

        defn = self.contractor_defs[idx]
        contractor = {
            "name": defn["name"],
            "color": defn["color"],
            "active_jobs": [],
            "jobs_completed": 0,
            "is_primary": is_primary,
            "spawn_time": datetime.now(timezone.utc).isoformat(),
        }
        self.active_contractors.append(contractor)
        kind = "primary" if is_primary else "on demand"
        logger.info(
            f"[{self.agent_id}] Contractor {defn['name']} spawned "
            f"({kind}) [{len(self.active_contractors)}/{self.max_contractors}]"
        )
        if not is_primary:
            self._record_event(
                "spawn", defn["name"], None,
                f"{defn['name']} spawned at {self.display_name} [{len(self.active_contractors)}/{self.max_contractors}]"
            )
        return contractor

    def _record_event(self, event_type: str, contractor_name: str,
                      claim_id: Optional[str], message: str):
        """Record an event in the shared event log (no lock required on pool)."""
        if self._event_log is not None and self._event_lock is not None:
            evt = ContractorEvent(self.agent_id, event_type, contractor_name,
                                 claim_id, message)
            with self._event_lock:
                self._event_log.appendleft(evt)

    def _add_job_to_contractor(self, contractor: dict, claim_id: str):
        """Add a job to a contractor's slot list (no lock)."""
        job = {
            "claim_id": claim_id,
            "progress_pct": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "processing",
        }
        contractor["active_jobs"].append(job)
        slots = len(contractor["active_jobs"])
        logger.info(
            f"[{self.agent_id}] Job {claim_id} assigned to {contractor['name']} "
            f"({slots}/{self.capacity})"
        )
        self._record_event(
            "job_assigned", contractor["name"], claim_id,
            f"{claim_id} assigned to {contractor['name']} at {self.display_name} ({slots}/{self.capacity})"
        )


# =============================================================================
# ContractorManager Singleton
# =============================================================================

class ContractorManager:
    """Singleton that manages all contractor pools across agent stages.

    Pools:
        - classifier: Claim Classifier (capacity=3, max=5)
        - adjudicator: Claim Adjudicator (capacity=3, max=5)
        - email_composer: Email Composer (capacity=5, max=3)
    """

    _instance: Optional["ContractorManager"] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if ContractorManager._initialized:
            return
        ContractorManager._initialized = True

        # Shared event log (ring buffer, newest-first)
        self._event_log: deque[ContractorEvent] = deque(maxlen=50)
        self._event_lock = threading.Lock()

        self.pools: dict[str, ContractorPool] = {
            "classifier": ContractorPool(
                agent_id="classifier",
                display_name="Claim Classifier",
                capacity=3,
                max_contractors=5,
                contractor_defs=[
                    {"name": "AIContractor Alice", "color": "#2dd4a8"},
                    {"name": "AIContractor Bob", "color": "#7c5cfc"},
                    {"name": "AIContractor Priya", "color": "#f59e0b"},
                    {"name": "AIContractor David", "color": "#38bdf8"},
                    {"name": "AIContractor Mei", "color": "#c084fc"},
                ],
                event_log=self._event_log,
                event_lock=self._event_lock,
            ),
            "adjudicator": ContractorPool(
                agent_id="adjudicator",
                display_name="Claim Adjudicator",
                capacity=3,
                max_contractors=5,
                contractor_defs=[
                    {"name": "AIContractor Alice", "color": "#2dd4a8"},
                    {"name": "AIContractor Bob", "color": "#7c5cfc"},
                    {"name": "AIContractor Priya", "color": "#f59e0b"},
                    {"name": "AIContractor David", "color": "#38bdf8"},
                    {"name": "AIContractor Mei", "color": "#c084fc"},
                ],
                event_log=self._event_log,
                event_lock=self._event_lock,
            ),
            "email_composer": ContractorPool(
                agent_id="email_composer",
                display_name="Email Composer",
                capacity=5,
                max_contractors=3,
                contractor_defs=[
                    {"name": "AIContractor Alice", "color": "#2dd4a8"},
                    {"name": "AIContractor Bob", "color": "#7c5cfc"},
                    {"name": "AIContractor Priya", "color": "#f59e0b"},
                ],
                event_log=self._event_log,
                event_lock=self._event_lock,
            ),
        }

        # HITL counter (tracked separately — not a contractor pool)
        self._hitl_waiting_count: int = 0
        self._hitl_lock = threading.Lock()

        # Email Received counter (tracked separately — not a contractor pool)
        self._email_received_count: int = 0
        self._email_received_lock = threading.Lock()

        # Email Sender counter (tracked separately — not a contractor pool)
        self._email_sending_count: int = 0
        self._email_sent_count: int = 0
        self._email_lock = threading.Lock()

        # Start progress simulation daemon thread
        self._progress_thread = threading.Thread(
            target=self._progress_simulation_loop,
            daemon=True,
            name="ContractorProgressSim",
        )
        self._progress_thread.start()

        logger.info("ContractorManager initialized with 3 pools + progress simulation")

    # =========================================================================
    # Pool Delegation
    # =========================================================================

    def assign_job(self, agent_id: str, claim_id: str) -> Optional[str]:
        """Assign a job to a contractor in the specified agent pool."""
        return self.pools[agent_id].assign_job(claim_id)

    def complete_job(self, agent_id: str, claim_id: str) -> bool:
        """Complete a job in the specified agent pool."""
        return self.pools[agent_id].complete_job(claim_id)

    def update_progress(self, agent_id: str, claim_id: str, progress_pct: int):
        """Update job progress in the specified agent pool."""
        self.pools[agent_id].update_progress(claim_id, progress_pct)

    # =========================================================================
    # Email Received Counter
    # =========================================================================

    def increment_email_received(self):
        """Increment the email received counter (claim entered the system)."""
        with self._email_received_lock:
            self._email_received_count += 1

    def decrement_email_received(self):
        """Decrement the email received counter (claim entered classifier)."""
        with self._email_received_lock:
            self._email_received_count = max(0, self._email_received_count - 1)

    def get_email_received_count(self) -> int:
        """Get current email received count."""
        with self._email_received_lock:
            return self._email_received_count

    # =========================================================================
    # HITL Counter
    # =========================================================================

    def increment_hitl_waiting(self):
        """Increment the HITL waiting counter (claim entered HITL stage)."""
        with self._hitl_lock:
            self._hitl_waiting_count += 1

    def decrement_hitl_waiting(self):
        """Decrement the HITL waiting counter (claim approved/rejected)."""
        with self._hitl_lock:
            self._hitl_waiting_count = max(0, self._hitl_waiting_count - 1)

    def get_hitl_waiting_count(self) -> int:
        """Get current HITL waiting count."""
        with self._hitl_lock:
            return self._hitl_waiting_count

    # =========================================================================
    # Email Sender Counter
    # =========================================================================

    def increment_email_sending(self):
        """Increment the email sending counter (email send started)."""
        with self._email_lock:
            self._email_sending_count += 1

    def decrement_email_sending(self):
        """Decrement the email sending counter and increment sent (email delivered)."""
        with self._email_lock:
            self._email_sending_count = max(0, self._email_sending_count - 1)
            self._email_sent_count += 1

    def get_email_sending_count(self) -> int:
        """Get current email sending count."""
        with self._email_lock:
            return self._email_sending_count

    def get_email_sent_count(self) -> int:
        """Get total emails sent."""
        with self._email_lock:
            return self._email_sent_count

    # =========================================================================
    # Progress Simulation
    # =========================================================================

    def _progress_simulation_loop(self):
        """Daemon thread: tick every 500ms, increment progress based on elapsed time."""
        while True:
            _time.sleep(PROGRESS_TICK_INTERVAL)
            now = datetime.now(timezone.utc)

            for agent_id, pool in self.pools.items():
                estimated = ESTIMATED_STAGE_DURATION_SECONDS.get(agent_id, 10)
                with pool._lock:
                    for contractor in pool.active_contractors:
                        for job in contractor["active_jobs"]:
                            if job["progress_pct"] >= PROGRESS_CAP:
                                continue
                            try:
                                started = datetime.fromisoformat(job["started_at"])
                                elapsed = (now - started).total_seconds()
                                pct = int((elapsed / estimated) * 100)
                                job["progress_pct"] = min(PROGRESS_CAP, max(0, pct))
                            except (ValueError, TypeError):
                                pass

    # =========================================================================
    # Event Log Access
    # =========================================================================

    def get_events(self) -> list[dict]:
        """Return the last 50 events as serializable dicts."""
        with self._event_lock:
            return [e.to_dict() for e in self._event_log]

    # =========================================================================
    # Global State
    # =========================================================================

    def get_all_state(self) -> dict:
        """Return full state across all pools for dashboard rendering.

        Returns:
            Dictionary with stages, hitl, and global counters
        """
        stages = {}
        total_in_flight = 0
        total_completed = 0

        for agent_id, pool in self.pools.items():
            state = pool.get_state()
            stages[agent_id] = state
            total_in_flight += state["total_jobs_in_flight"]
            total_completed += state["total_completed"]

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stages": stages,
            "email_receiver": {
                "display_name": "Email Received",
                "received_count": self.get_email_received_count(),
            },
            "hitl": {
                "display_name": "Manual Estimate",
                "waiting_count": self.get_hitl_waiting_count(),
            },
            "email_sender": {
                "display_name": "Email Sender",
                "sending_count": self.get_email_sending_count(),
                "sent_count": self.get_email_sent_count(),
            },
            "global": {
                "total_claims_in_flight": total_in_flight,
                "total_claims_completed": total_completed,
            },
            "events": self.get_events(),
        }

    # =========================================================================
    # Reset (for testing)
    # =========================================================================

    @classmethod
    def reset(cls):
        """Reset the singleton for testing purposes."""
        cls._instance = None
        cls._initialized = False
