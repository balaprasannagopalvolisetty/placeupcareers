"""
Tier C headless browser worker (Playwright) — scaffold + handoff state machine.

For the ~18 web-form-only platforms, submission runs in a Playwright container
on Cloud Run Jobs (batch) or a Cloud Run service (interactive handoff). This
module defines the worker contract and the graceful-handoff state machine; the
actual Playwright driver is behind `_PlaywrightDriver` so the state logic is
testable without a browser and the container image stays optional.

Non-negotiable rules from the doc, encoded here:
  * The worker fills the form up to — but NOT including — the final submit,
    then pauses at NEEDS_REVIEW for human approval.
  * On a CAPTCHA / bot-check / OTP prompt it sets NEEDS_YOU, freezes
    automation, and opens a live view. It NEVER solves or bypasses the control.
  * `browser.close()` always runs in a finally block (no zombie/OOM cascade).
  * Budget >=2 vCPU / 2 GiB per browser; enlarge /dev/shm.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from app.models.application import ApplicationStatus

log = logging.getLogger("placeup.apply.browser")


class HandoffTrigger(str, Enum):
    CAPTCHA = "captcha"
    OTP = "otp"
    BOT_CHECK = "bot_check"
    NONE = "none"


@dataclass
class BrowserStepResult:
    status: ApplicationStatus
    handoff: HandoffTrigger = HandoffTrigger.NONE
    screenshot_url: Optional[str] = None
    confirmation_ref: Optional[str] = None
    message: str = ""


@dataclass
class _PlaywrightDriver:
    """Thin seam over Playwright so the worker's logic is unit-testable.

    In production this launches slim Chromium (`@sparticuz/chromium` /
    `playwright-core`) or connects to a managed browser (Steel.dev /
    Browserbase). Here it is a no-op placeholder that reports 'unavailable'
    unless a real driver is injected.
    """

    available: bool = False

    async def open(self, url: str) -> None:  # pragma: no cover - network
        raise RuntimeError("Playwright driver not installed in this environment")

    async def fill_form(self, config: dict, payload: dict) -> HandoffTrigger:  # pragma: no cover
        raise RuntimeError("Playwright driver not installed in this environment")

    async def detect_challenge(self) -> HandoffTrigger:  # pragma: no cover
        return HandoffTrigger.NONE

    async def screenshot(self) -> Optional[str]:  # pragma: no cover
        return None

    async def click_submit(self) -> Optional[str]:  # pragma: no cover
        return None

    async def close(self) -> None:  # pragma: no cover
        return None


class BrowserApplyWorker:
    """Drives one Tier C application through the review + handoff state machine.

    `on_frame` is an optional callback used by the handoff bridge to relay CDP
    screencast frames to the client over WebSocket.
    """

    def __init__(self, driver: Optional[_PlaywrightDriver] = None,
                 on_frame: Optional[Callable[[bytes], None]] = None):
        self.driver = driver or _PlaywrightDriver()
        self.on_frame = on_frame

    async def prepare(self, job_url: str, adapter_config: dict, payload: dict) -> BrowserStepResult:
        """Fill everything up to the final submit, then stop for review.

        Returns NEEDS_YOU immediately if a challenge appears while filling
        (e.g. Workday bot-check on load), otherwise NEEDS_REVIEW.
        """
        if not self.driver.available:
            # Honest failure: no browser here -> route to manual handoff.
            return BrowserStepResult(
                status=ApplicationStatus.NEEDS_YOU,
                handoff=HandoffTrigger.BOT_CHECK,
                message="No headless browser available; user must complete manually.",
            )
        try:  # pragma: no cover - requires Playwright
            await self.driver.open(job_url)
            trigger = await self.driver.fill_form(adapter_config, payload)
            if trigger is not HandoffTrigger.NONE:
                shot = await self.driver.screenshot()
                return BrowserStepResult(
                    status=ApplicationStatus.NEEDS_YOU, handoff=trigger,
                    screenshot_url=shot, message=f"Handoff required: {trigger.value}",
                )
            shot = await self.driver.screenshot()
            return BrowserStepResult(
                status=ApplicationStatus.NEEDS_REVIEW, screenshot_url=shot,
                message="Form filled up to submit; awaiting review.",
            )
        finally:  # pragma: no cover
            # Never leak a browser process.
            await self.driver.close()

    async def submit(self, job_url: str, adapter_config: dict, payload: dict) -> BrowserStepResult:
        """Runs ONLY after human approval. Clicks submit; captures the
        confirmation screenshot; hands off if a late challenge appears."""
        if not self.driver.available:
            return BrowserStepResult(
                status=ApplicationStatus.NEEDS_YOU,
                handoff=HandoffTrigger.BOT_CHECK,
                message="No headless browser available; user must submit manually.",
            )
        try:  # pragma: no cover - requires Playwright
            await self.driver.open(job_url)
            await self.driver.fill_form(adapter_config, payload)
            challenge = await self.driver.detect_challenge()
            if challenge is not HandoffTrigger.NONE:
                return BrowserStepResult(
                    status=ApplicationStatus.NEEDS_YOU, handoff=challenge,
                    screenshot_url=await self.driver.screenshot(),
                )
            ref = await self.driver.click_submit()
            return BrowserStepResult(
                status=ApplicationStatus.APPLIED, confirmation_ref=ref,
                screenshot_url=await self.driver.screenshot(),
                message="Submitted.",
            )
        finally:  # pragma: no cover
            await self.driver.close()
