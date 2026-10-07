"""Fetch-or-404 helpers shared by the routers."""

from fastapi import HTTPException, status

from app import data


def get_cohort_or_404(cohort_id: str) -> dict:
    cohort = data.COHORTS.get(cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Cohort '{cohort_id}' not found")
    return cohort


def get_trainee_or_404(trainee_id: str) -> dict:
    user = data.USERS.get(trainee_id)
    if user is None or user["role"] != "trainee":
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Trainee '{trainee_id}' not found")
    return user
