"""Hermes profile helpers for the web chat API."""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable

from fastapi import HTTPException, status

from .models import SwitchProfileRequest, SwitchProfileResponse, WebChatProfile, WebChatProfilesResponse


def profile_dependencies():
    from hermes_cli.profiles import (
        get_active_profile,
        list_profiles,
        profile_exists,
        resolve_profile_env,
        set_active_profile,
        validate_profile_name,
    )

    return get_active_profile, list_profiles, profile_exists, resolve_profile_env, set_active_profile, validate_profile_name


def list_web_chat_profiles(
    profile_dependencies_func: Callable[[], tuple] = profile_dependencies,
) -> WebChatProfilesResponse:
    try:
        get_active_profile, list_profiles, _, _, _, _ = profile_dependencies_func()
        active = get_active_profile()
        profiles = [
            WebChatProfile(
                id=profile.name,
                label=profile.name,
                path=str(profile.path),
                active=profile.name == active,
            )
            for profile in list_profiles()
        ]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not load Hermes profiles: {exc}",
        ) from exc

    return WebChatProfilesResponse(profiles=profiles, activeProfile=active)


def restart_backend_soon() -> None:
    def restart() -> None:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)

    threading.Timer(0.35, restart).start()


def switch_web_chat_profile(
    payload: SwitchProfileRequest,
    *,
    has_running_runs: Callable[[], bool],
    restart_backend: Callable[[], None] = restart_backend_soon,
    profile_dependencies_func: Callable[[], tuple] = profile_dependencies,
) -> SwitchProfileResponse:
    requested = payload.profile.strip()
    try:
        get_active_profile, list_profiles, profile_exists, resolve_profile_env, set_active_profile, validate_profile_name = profile_dependencies_func()
        validate_profile_name(requested)
        if not profile_exists(requested):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hermes profile does not exist")
        resolve_profile_env(requested)
        current = get_active_profile()
        profiles = list_profiles()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not switch Hermes profile: {exc}") from exc

    if requested != current and has_running_runs():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Wait for running chats to finish before switching profiles.")

    if requested != current:
        try:
            set_active_profile(requested)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not switch Hermes profile: {exc}") from exc

        if payload.restart:
            restart_backend()

    return SwitchProfileResponse(
        profiles=[
            WebChatProfile(
                id=profile.name,
                label=profile.name,
                path=str(profile.path),
                active=profile.name == requested,
            )
            for profile in profiles
        ],
        activeProfile=requested,
        restarting=payload.restart and requested != current,
    )


def validate_profile(
    profile: str | None,
    profile_dependencies_func: Callable[[], tuple] = profile_dependencies,
) -> str | None:
    requested = str(profile or "").strip()
    if not requested:
        return None

    try:
        get_active_profile, _, profile_exists, _, _, validate_profile_name = profile_dependencies_func()
        validate_profile_name(requested)
        if not profile_exists(requested):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hermes profile does not exist")
        active = get_active_profile()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not validate Hermes profile: {exc}") from exc

    if requested != active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Switching Hermes profile requires a backend restart in this prototype. Current profile: {active}.",
        )
    return requested
