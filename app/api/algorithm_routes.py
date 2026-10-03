"""Bounded deterministic computation endpoints, separate from LLM execution."""
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from app.service.research_algorithms import (
    RegimeInput, CovarianceInput, FiveFactorInput,
    regime_probabilities, constant_correlation_shrinkage, five_factors,
)


def create_algorithm_router(owner_dependency):
    router = APIRouter(prefix="/api/v1/research/algorithms", tags=["research-algorithms"])
    capacity = asyncio.Semaphore(2)

    async def calculate(function, body):
        try:
            async with capacity:
                task = asyncio.create_task(asyncio.to_thread(function, body))
                try:
                    return await asyncio.shield(task)
                except asyncio.CancelledError:
                    # Keep capacity until the non-interruptible numerical worker exits.
                    await task
                    raise
        except (ValueError, ArithmeticError):
            raise HTTPException(422, detail="ALGORITHM_INPUT_INVALID") from None

    @router.post("/regime")
    async def regime(body: RegimeInput, owner_id=Depends(owner_dependency)):
        return await calculate(regime_probabilities, body)

    @router.post("/covariance")
    async def covariance(body: CovarianceInput, owner_id=Depends(owner_dependency)):
        return await calculate(constant_correlation_shrinkage, body)

    @router.post("/five-factors")
    async def factors(body: FiveFactorInput, owner_id=Depends(owner_dependency)):
        return await calculate(five_factors, body)

    return router
