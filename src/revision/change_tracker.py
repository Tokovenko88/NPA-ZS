"""Отслеживание изменений через все стадии пайплайна.

Гарантирует, что каждое изменение из Stage 3 проходит через:
  extracted -> applying -> prepared -> applied -> verified

Любое отклонение (pending, failed, lost, unverified) приводит к FAILED статусу.
"""

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional


class ChangeStatus(str, Enum):
    EXTRACTED = "extracted"
    APPLYING = "applying"
    PREPARED = "prepared"
    APPLIED = "applied"
    VERIFIED = "verified"
    PENDING = "pending"
    FAILED = "failed"
    LOST = "lost"
    UNVERIFIED = "unverified"
    USER_CANCELLED_ADDRESS_SELECTION = "user_cancelled_address_selection"
    NEEDS_USER_ADDRESS = "needs_user_address"


_ALLOWED_TRANSITIONS = {
    ChangeStatus.EXTRACTED: {ChangeStatus.APPLYING, ChangeStatus.PENDING, ChangeStatus.USER_CANCELLED_ADDRESS_SELECTION, ChangeStatus.NEEDS_USER_ADDRESS},
    ChangeStatus.APPLYING: {ChangeStatus.PREPARED, ChangeStatus.APPLIED, ChangeStatus.FAILED, ChangeStatus.PENDING, ChangeStatus.USER_CANCELLED_ADDRESS_SELECTION, ChangeStatus.NEEDS_USER_ADDRESS},
    ChangeStatus.PREPARED: {ChangeStatus.APPLIED, ChangeStatus.FAILED, ChangeStatus.PENDING, ChangeStatus.USER_CANCELLED_ADDRESS_SELECTION, ChangeStatus.NEEDS_USER_ADDRESS},
    ChangeStatus.APPLIED: {ChangeStatus.VERIFIED, ChangeStatus.FAILED},
    ChangeStatus.VERIFIED: set(),
    ChangeStatus.PENDING: {ChangeStatus.FAILED},
    ChangeStatus.FAILED: set(),
    ChangeStatus.LOST: {ChangeStatus.FAILED},
    ChangeStatus.UNVERIFIED: {ChangeStatus.VERIFIED, ChangeStatus.FAILED},
    ChangeStatus.USER_CANCELLED_ADDRESS_SELECTION: set(),
    ChangeStatus.NEEDS_USER_ADDRESS: {ChangeStatus.APPLYING, ChangeStatus.USER_CANCELLED_ADDRESS_SELECTION, ChangeStatus.FAILED},
}


class ChangeTracker:
    """Трекер изменений для контроля полноты применения."""

    def __init__(self, log_callback=None):
        self._changes: Dict[str, Dict[str, Any]] = {}
        self._log_callback = log_callback

    def _log(self, message: str, level: str = 'info'):
        if self._log_callback:
            self._log_callback(message, level)

    def _transition(self, change_id: str, new_status: ChangeStatus):
        current = self._changes[change_id]["status"]
        allowed = _ALLOWED_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition for {change_id}: {current.value} -> {new_status.value}"
            )

    def register_change(self, change: Dict[str, Any]) -> str:
        """Регистрирует изменение и возвращает его change_id."""
        change_id = str(uuid.uuid4())[:12]
        self._changes[change_id] = {
            "change_id": change_id,
            "revision_number": change.get("revision_number", ""),
            "structural_element": change.get("structural_element", ""),
            "type": change.get("type", ""),
            "status": ChangeStatus.EXTRACTED,
            "source_change": change,
            "target_item_id": None,
            "revision_id": None,
            "error_reason": None,
            "verification_result": None,
        }
        change["change_id"] = change_id
        self._log(
            f"CHANGE [{change_id}] "
            f"revision_number: {change.get('revision_number', '')} "
            f"structural_element: {change.get('structural_element', '')} "
            f"type: {change.get('type', '')} "
            f"status: EXTRACTED "
            f"revision_id: None"
        )
        return change_id

    def mark_applying(self, change_id: str, target_item_id: str = None):
        """Отмечает изменение как находящееся в процессе применения."""
        if change_id in self._changes:
            self._transition(change_id, ChangeStatus.APPLYING)
            self._changes[change_id]["status"] = ChangeStatus.APPLYING
            if target_item_id:
                self._changes[change_id]["target_item_id"] = target_item_id
            self._log(
                f"CHANGE [{change_id}] "
                f"revision_number: {self._changes[change_id]['revision_number']} "
                f"status: APPLYING, target_item_id: {target_item_id}"
            )

    def mark_prepared(self, change_id: str, target_item_id: str = None):
        """Отмечает изменение как подготовленное к перестройке (PREPARED)."""
        if change_id in self._changes:
            self._transition(change_id, ChangeStatus.PREPARED)
            self._changes[change_id]["status"] = ChangeStatus.PREPARED
            if target_item_id:
                self._changes[change_id]["target_item_id"] = target_item_id
            self._log(
                f"CHANGE [{change_id}] "
                f"revision_number: {self._changes[change_id]['revision_number']} "
                f"status: PREPARED, target_item_id: {target_item_id}"
            )

    def mark_applied(self, change_id: str, revision_id: str = None, target_item_id: str = None):
        """Отмечает изменение как применённое. Требует revision_id."""
        if change_id not in self._changes:
            return
        if not revision_id:
            self.mark_failed(change_id, "Cannot mark change as APPLIED without revision_id")
            return
        self._transition(change_id, ChangeStatus.APPLIED)
        self._changes[change_id]["status"] = ChangeStatus.APPLIED
        self._changes[change_id]["revision_id"] = revision_id
        if target_item_id:
            self._changes[change_id]["target_item_id"] = target_item_id
        self._log(
            f"CHANGE [{change_id}] "
            f"revision_number: {self._changes[change_id]['revision_number']} "
            f"status: APPLIED "
            f"revision_id: {revision_id}"
        )

    def mark_verified(self, change_id: str, verification_result: Any = None):
        """Отмечает изменение как проверенное."""
        if change_id in self._changes:
            self._transition(change_id, ChangeStatus.VERIFIED)
            self._changes[change_id]["status"] = ChangeStatus.VERIFIED
            self._changes[change_id]["verification_result"] = verification_result
            self._log(
                f"CHANGE [{change_id}] "
                f"revision_number: {self._changes[change_id]['revision_number']} "
                f"status: VERIFIED "
                f"revision_id: {self._changes[change_id]['revision_id']}"
            )

    def mark_failed(self, change_id: str, reason: str):
        """Отмечает изменение как failed."""
        if change_id in self._changes:
            self._changes[change_id]["status"] = ChangeStatus.FAILED
            self._changes[change_id]["error_reason"] = reason
            self._log(
                f"CHANGE [{change_id}] "
                f"revision_number: {self._changes[change_id]['revision_number']} "
                f"status: FAILED, reason: {reason}",
                'error'
            )

    def mark_pending(self, change_id: str, reason: str = ""):
        """Отмечает изменение как pending (не применённое)."""
        if change_id in self._changes:
            self._transition(change_id, ChangeStatus.PENDING)
            self._changes[change_id]["status"] = ChangeStatus.PENDING
            self._changes[change_id]["error_reason"] = reason
            self._log(
                f"CHANGE [{change_id}] "
                f"revision_number: {self._changes[change_id]['revision_number']} "
                f"status: PENDING, reason: {reason}",
                'warning'
            )

    def mark_user_cancelled(self, change_id: str, reason: str = ""):
        """Отмечает изменение как отменённое пользователем при выборе адреса."""
        if change_id in self._changes:
            self._transition(change_id, ChangeStatus.USER_CANCELLED_ADDRESS_SELECTION)
            self._changes[change_id]["status"] = ChangeStatus.USER_CANCELLED_ADDRESS_SELECTION
            self._changes[change_id]["error_reason"] = reason
            self._log(
                f"CHANGE [{change_id}] "
                f"revision_number: {self._changes[change_id]['revision_number']} "
                f"status: USER_CANCELLED_ADDRESS_SELECTION, reason: {reason}",
                'warning'
            )

    def mark_needs_user_address(self, change_id: str, reason: str = ""):
        """Отмечает изменение как ожидающее выбора адреса пользователем."""
        if change_id in self._changes:
            self._transition(change_id, ChangeStatus.NEEDS_USER_ADDRESS)
            self._changes[change_id]["status"] = ChangeStatus.NEEDS_USER_ADDRESS
            self._changes[change_id]["error_reason"] = reason
            self._log(
                f"CHANGE [{change_id}] "
                f"revision_number: {self._changes[change_id]['revision_number']} "
                f"status: NEEDS_USER_ADDRESS, reason: {reason}",
                'warning'
            )

    def get_status(self, change_id: str) -> Optional[str]:
        """Возвращает статус изменения."""
        if change_id in self._changes:
            return self._changes[change_id]["status"]
        return None

    def get_change(self, change_id: str) -> Optional[Dict[str, Any]]:
        """Возвращает полную информацию об изменении."""
        return self._changes.get(change_id)

    def get_all_changes(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает все изменения."""
        return dict(self._changes)

    def get_changes_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Возвращает изменения по статусу."""
        return [c for c in self._changes.values() if c["status"] == status]

    @property
    def expected_count(self) -> int:
        """Ожидаемое количество изменений."""
        return len(self._changes)

    @property
    def applied_count(self) -> int:
        """Количество применённых изменений."""
        return len(self.get_changes_by_status(ChangeStatus.APPLIED)) + \
               len(self.get_changes_by_status(ChangeStatus.VERIFIED))

    @property
    def verified_count(self) -> int:
        """Количество проверенных изменений."""
        return len(self.get_changes_by_status(ChangeStatus.VERIFIED))

    @property
    def prepared_count(self) -> int:
        """Количество подготовленных, но не применённых изменений."""
        return len(self.get_changes_by_status(ChangeStatus.PREPARED))

    @property
    def pending_count(self) -> int:
        """Количество pending изменений."""
        return len(self.get_changes_by_status(ChangeStatus.PENDING))

    @property
    def failed_count(self) -> int:
        """Количество failed изменений."""
        return len(self.get_changes_by_status(ChangeStatus.FAILED))

    @property
    def lost_count(self) -> int:
        """Количество lost изменений (не удалось отследить)."""
        return len(self.get_changes_by_status(ChangeStatus.LOST))

    @property
    def unverified_count(self) -> int:
        """Количество applied, но не verified изменений."""
        return len(self.get_changes_by_status(ChangeStatus.APPLIED))

    @property
    def user_cancelled_count(self) -> int:
        """Количество отменённых пользователем изменений."""
        return len(self.get_changes_by_status(ChangeStatus.USER_CANCELLED_ADDRESS_SELECTION))

    @property
    def needs_user_address_count(self) -> int:
        """Количество изменений, ожидающих выбора адреса пользователем."""
        return len(self.get_changes_by_status(ChangeStatus.NEEDS_USER_ADDRESS))

    def compute_summary(self) -> Dict[str, Any]:
        """Вычисляет итоговую статистику."""
        return {
            "expected": self.expected_count,
            "prepared": self.prepared_count,
            "applied": self.applied_count,
            "verified": self.verified_count,
            "pending": self.pending_count,
            "failed": self.failed_count,
            "lost": self.lost_count,
            "unverified": self.unverified_count,
            "user_cancelled": self.user_cancelled_count,
            "needs_user_address": self.needs_user_address_count,
        }

    @property
    def applying_count(self) -> int:
        """Количество изменений в состоянии APPLYING."""
        return len(self.get_changes_by_status(ChangeStatus.APPLYING))

    def compute_run_status(self) -> str:
        """Вычисляет итоговый статус запуска.

        Правило: если хотя бы одно изменение не verified -> FAILED.
        """
        if self.expected_count == 0:
            return "SUCCESS"

        if self.applying_count > 0:
            return "FAILED"
        if self.prepared_count > 0:
            return "FAILED"
        if self.failed_count > 0:
            return "FAILED"
        if self.pending_count > 0:
            return "FAILED"
        if self.lost_count > 0:
            return "FAILED"
        if self.unverified_count > 0:
            return "FAILED"
        if self.user_cancelled_count > 0:
            return "FAILED"
        if self.needs_user_address_count > 0:
            return "FAILED"
        if self.verified_count != self.expected_count:
            return "FAILED"
        return "SUCCESS"

    def get_run_status_report(self) -> Dict[str, Any]:
        """Возвращает полный отчёт о статусе запуска."""
        summary = self.compute_summary()
        status = self.compute_run_status()
        failed_changes = self.get_changes_by_status(ChangeStatus.FAILED)
        pending_changes = self.get_changes_by_status(ChangeStatus.PENDING)
        unverified_changes = self.get_changes_by_status(ChangeStatus.APPLIED)
        prepared_changes = self.get_changes_by_status(ChangeStatus.PREPARED)
        user_cancelled_changes = self.get_changes_by_status(ChangeStatus.USER_CANCELLED_ADDRESS_SELECTION)

        report = {
            "run_status": status,
            "summary": summary,
            "failed_changes": [
                {
                    "change_id": c["change_id"],
                    "revision_number": c["revision_number"],
                    "structural_element": c["structural_element"],
                    "type": c["type"],
                    "reason": c["error_reason"],
                }
                for c in failed_changes
            ],
            "pending_changes": [
                {
                    "change_id": c["change_id"],
                    "revision_number": c["revision_number"],
                    "structural_element": c["structural_element"],
                    "type": c["type"],
                    "reason": c["error_reason"],
                }
                for c in pending_changes
            ],
            "prepared_changes": [
                {
                    "change_id": c["change_id"],
                    "revision_number": c["revision_number"],
                    "structural_element": c["structural_element"],
                    "type": c["type"],
                }
                for c in prepared_changes
            ],
            "unverified_changes": [
                {
                    "change_id": c["change_id"],
                    "revision_number": c["revision_number"],
                    "structural_element": c["structural_element"],
                    "type": c["type"],
                }
                for c in unverified_changes
            ],
            "user_cancelled_changes": [
                {
                    "change_id": c["change_id"],
                    "revision_number": c["revision_number"],
                    "structural_element": c["structural_element"],
                    "type": c["type"],
                    "reason": c["error_reason"],
                }
                for c in user_cancelled_changes
            ],
        }
        return report

    def print_summary(self):
        """Выводит итоговую статистику в лог."""
        summary = self.compute_summary()
        status = self.compute_run_status()

        self._log("CHANGE SUMMARY", 'result')
        self._log(f"  expected: {summary['expected']}", 'result')
        self._log(f"  prepared: {summary['prepared']}", 'result')
        self._log(f"  applied: {summary['applied']}", 'result')
        self._log(f"  verified: {summary['verified']}", 'result')
        self._log(f"  pending: {summary['pending']}", 'result')
        self._log(f"  failed: {summary['failed']}", 'result')
        self._log(f"  lost: {summary['lost']}", 'result')
        self._log(f"  user_cancelled: {summary['user_cancelled']}", 'result')
        self._log(f"RUN STATUS: {status}", 'result' if status == "SUCCESS" else 'error')

        if status == "FAILED":
            failed = self.get_changes_by_status(ChangeStatus.FAILED)
            pending = self.get_changes_by_status(ChangeStatus.PENDING)
            unverified = self.get_changes_by_status(ChangeStatus.APPLIED)
            prepared = self.get_changes_by_status(ChangeStatus.PREPARED)
            user_cancelled = self.get_changes_by_status(ChangeStatus.USER_CANCELLED_ADDRESS_SELECTION)
            needs_user_address = self.get_changes_by_status(ChangeStatus.NEEDS_USER_ADDRESS)

            if prepared:
                self._log("Prepared changes:", 'warning')
                for c in prepared:
                    self._log(
                        f"  [{c['revision_number']}] {c['structural_element']} "
                        f"(type={c['type']})",
                        'warning'
                    )
            if failed:
                self._log("Failed changes:", 'error')
                for c in failed:
                    self._log(
                        f"  [{c['revision_number']}] {c['structural_element']} "
                        f"(type={c['type']}): {c['error_reason']}",
                        'error'
                    )
            if pending:
                self._log("Pending changes:", 'warning')
                for c in pending:
                    self._log(
                        f"  [{c['revision_number']}] {c['structural_element']} "
                        f"(type={c['type']}): {c['error_reason']}",
                        'warning'
                    )
            if unverified:
                self._log("Unverified changes:", 'warning')
                for c in unverified:
                    self._log(
                        f"  [{c['revision_number']}] {c['structural_element']} "
                        f"(type={c['type']})",
                        'warning'
                    )
            if user_cancelled:
                self._log("User cancelled changes:", 'warning')
                for c in user_cancelled:
                    self._log(
                        f"  [{c['revision_number']}] {c['structural_element']} "
                        f"(type={c['type']}): {c['error_reason']}",
                        'warning'
                    )
            if needs_user_address:
                self._log("Needs user address changes:", 'warning')
                for c in needs_user_address:
                    self._log(
                        f"  [{c['revision_number']}] {c['structural_element']} "
                        f"(type={c['type']}): {c['error_reason']}",
                        'warning'
                    )
