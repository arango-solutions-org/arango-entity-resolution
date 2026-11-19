"""Per-level ``u`` must be MEASURED on random pairs, not inferred by EM.

The binary path already estimates ``u = P(agree | non-match)`` by counting
agreement among random record pairs, because candidate pairs have all cleared a
similarity gate and so cannot furnish a representative non-match sample. Joint EM
over candidates alone drove one match weight to 27.6 nats (e^27 odds) against
0.727 nats with ``u`` anchored.

The categorical path shipped without that correction, rationalised in a comment
as impossible: a scalar agreement rate "cannot be spread across levels without
inventing a shape". That reasoning is wrong, and these tests pin why — no
spreading is needed, because the entire level distribution is directly
observable. Score random pairs, bin each field with the same ``assign_level`` the
estimator uses, and count.

These are the properties that make the measurement trustworthy rather than merely
present: it bins through the shared function, it ignores unobserved fields, it
keeps every level positive so no log(m/u) goes infinite, and it omits a field it
never saw instead of inventing a distribution for it.
"""

from __future__ import annotations

import math

import pytest

from entity_resolution.learning.em_estimator import assign_level
from entity_resolution.learning.model_parameter_estimator import (
    categorical_u_from_comparisons,
)

pytestmark = pytest.mark.unit

# Two bands plus a fallback, the shape the estimator and scorer both consume:
# most selective first, final level's min_similarity None.
LEVELS = {
    "name": [
        {"name": "exact", "min_similarity": 0.9},
        {"name": "close", "min_similarity": 0.6},
        {"name": "else", "min_similarity": None},
    ]
}
FIELDS = ["name"]


def test_counts_become_the_level_distribution():
    """The core claim: level frequencies among random pairs ARE u."""
    comparisons = (
        [{"name": 0.95}] * 10      # exact
        + [{"name": 0.7}] * 30     # close
        + [{"name": 0.1}] * 60     # else
    )
    u = categorical_u_from_comparisons(comparisons, LEVELS, FIELDS)

    # 100 observations, 3 levels -> Laplace denominator 103.
    assert u["name"] == pytest.approx([11 / 103, 31 / 103, 61 / 103])
    assert sum(u["name"]) == pytest.approx(1.0)


def test_probabilities_sum_to_one_exactly_enough_for_the_scorer():
    """The scorer validates that level probabilities sum to 1."""
    comparisons = [{"name": v} for v in (0.99, 0.95, 0.8, 0.65, 0.4, 0.0, 0.3)]
    u = categorical_u_from_comparisons(comparisons, LEVELS, FIELDS)
    assert sum(u["name"]) == pytest.approx(1.0, abs=1e-12)


def test_unobserved_fields_do_not_inflate_the_fallback_level():
    """A missing field is not a disagreement — the null-level convention.

    Counting ``None`` as the fallback level would make sparse data look like
    chance disagreement and push u's mass to the bottom band, understating how
    surprising a real disagreement is.
    """
    observed_only = [{"name": 0.95}] * 5 + [{"name": 0.1}] * 5
    with_missing = observed_only + [{"name": None}] * 50 + [{}] * 50

    got = categorical_u_from_comparisons(with_missing, LEVELS, FIELDS)
    want = categorical_u_from_comparisons(observed_only, LEVELS, FIELDS)
    # Per field: pytest >= 9.2 refuses approx() over a dict of lists.
    assert got.keys() == want.keys()
    for field in want:
        assert got[field] == pytest.approx(want[field])


def test_every_level_keeps_positive_mass_so_no_weight_is_infinite():
    """A level absent from the sample must not take probability zero.

    log(m/u) with u = 0 is infinite, which poisons every score for a pair landing
    in that level — and the sample legitimately may never produce a band that
    only true matches reach.
    """
    comparisons = [{"name": 0.1}] * 200  # nothing ever reaches exact or close
    u = categorical_u_from_comparisons(comparisons, LEVELS, FIELDS)

    assert all(p > 0 for p in u["name"]), u["name"]
    assert all(math.isfinite(math.log(p)) for p in u["name"])
    # The unseen levels get the smallest possible share, not an equal one.
    assert u["name"][0] == u["name"][1] < u["name"][2]


def test_field_never_observed_is_omitted_not_defaulted():
    """Omission routes the field to joint EM; a default would fake a measurement.

    ``estimate_categorical_mu`` skips fields absent from ``fixed_u``, so leaving
    one out is how a field with no evidence keeps being estimated rather than
    being handed an invented distribution labelled as measured.
    """
    levels = dict(LEVELS)
    levels["ghost"] = LEVELS["name"]
    comparisons = [{"name": 0.95, "ghost": None}] * 20

    u = categorical_u_from_comparisons(comparisons, levels, ["name", "ghost"])

    assert "name" in u
    assert "ghost" not in u


def test_fields_without_configured_levels_are_skipped():
    """A partially-configured model must not mix comparison models silently."""
    comparisons = [{"name": 0.95, "unbanded": 0.95}] * 10
    u = categorical_u_from_comparisons(comparisons, LEVELS, ["name", "unbanded"])
    assert set(u) == {"name"}


def test_no_comparisons_yields_no_measurement():
    assert categorical_u_from_comparisons([], LEVELS, FIELDS) == {}


def test_per_field_denominators_are_independent():
    """One field's sparsity must not distort another's distribution.

    A shared denominator would make a frequently-empty field look like a
    frequently-disagreeing one — the same per-field denominator property the
    binary M-step needs.
    """
    levels = {"a": LEVELS["name"], "b": LEVELS["name"]}
    comparisons = [{"a": 0.95, "b": None}] * 10 + [{"a": 0.95, "b": 0.95}] * 10

    u = categorical_u_from_comparisons(comparisons, levels, ["a", "b"])

    assert u["a"] == pytest.approx([21 / 23, 1 / 23, 1 / 23])
    assert u["b"] == pytest.approx([11 / 13, 1 / 13, 1 / 13])


def test_binning_matches_assign_level_at_band_edges():
    """Training and scoring must never bin the same similarity differently.

    Rather than restating the boundary rule (and risking restating it wrongly),
    this asserts agreement with the shared function at exactly the values where
    an off-by-one would hide.
    """
    thresholds = [lvl["min_similarity"] for lvl in LEVELS["name"]]
    edges = [0.0, 0.5999, 0.6, 0.6001, 0.8999, 0.9, 0.9001, 1.0]

    for value in edges:
        expected = assign_level(value, thresholds)
        u = categorical_u_from_comparisons([{"name": value}], LEVELS, FIELDS)
        # One observation, so the counted level is the one with the extra mass.
        counted = max(range(3), key=lambda i: u["name"][i])
        assert counted == expected, f"{value} binned to {counted}, assign_level says {expected}"


def test_measured_u_is_lower_than_candidate_biased_u_for_selective_levels():
    """The bias this fix exists to remove, stated as a property.

    Candidate pairs are enriched for agreement, so estimating u there overstates
    how often a selective level occurs by chance — which compresses log(m/u) and
    costs the model discrimination. Measuring on random pairs must give the
    selective level LESS mass than the candidate population does.
    """
    random_pairs = [{"name": 0.1}] * 90 + [{"name": 0.95}] * 10
    candidate_pairs = [{"name": 0.1}] * 30 + [{"name": 0.95}] * 70

    measured = categorical_u_from_comparisons(random_pairs, LEVELS, FIELDS)
    biased = categorical_u_from_comparisons(candidate_pairs, LEVELS, FIELDS)

    assert measured["name"][0] < biased["name"][0], (
        "random-pair u must assign less chance mass to the exact level than the "
        "blocking-enriched candidate population does"
    )


# ---------------------------------------------------------------------------
# Degeneracy alarm when a supplied fixed u does not fit the pair population
# ---------------------------------------------------------------------------


def _two_level(n_fields):
    return {f"f{i}": ["agree", "else"] for i in range(n_fields)}


def test_implausible_match_prior_is_flagged_when_u_is_fixed():
    """A fixed u that misdescribes the population must not fail silently.

    Holding u constant removes label-switch resolution as an escape route, so a
    bad fit surfaces as an absurd match prior instead. Measured on FEBRL
    dataset3: lambda converged to 0.925 against 0.099 for the same data with u
    estimated jointly, and that model scored F1 0.26 with B-cubed 0.001. Nothing
    detected it.
    """
    import numpy as np

    from entity_resolution.learning.em_estimator import estimate_categorical_mu

    # Every pair agrees everywhere, while the supplied u insists agreement is
    # near-certain by chance. The only fit left is "almost all of this is a match".
    gamma = np.zeros((200, 3))
    result = estimate_categorical_mu(
        gamma,
        _two_level(3),
        fixed_u={f"f{i}": [0.99, 0.01] for i in range(3)},
        init_lambda=0.5,
    )

    assert result.lambda_ > 0.5, f"fixture did not reproduce the failure: {result.lambda_}"
    assert result.warning is not None, "degenerate fit reported no warning"
    assert "match prior" in result.warning
    assert result.to_dict()["warning"] == result.warning


def test_a_healthy_fixed_u_fit_is_not_flagged():
    """The alarm must stay quiet on a well-separated fit, or it is noise."""
    import numpy as np

    from entity_resolution.learning.em_estimator import estimate_categorical_mu

    # 20 agreeing pairs among 200: a normal post-blocking match rate.
    gamma = np.ones((200, 3))
    gamma[:20] = 0.0
    result = estimate_categorical_mu(
        gamma,
        _two_level(3),
        fixed_u={f"f{i}": [0.01, 0.99] for i in range(3)},
    )

    assert result.lambda_ < 0.5, result.lambda_
    assert result.warning is None, result.warning


def test_jointly_estimated_u_is_not_subject_to_the_alarm():
    """Joint EM resolves label switching by swapping, so the alarm is inapplicable."""
    import numpy as np

    from entity_resolution.learning.em_estimator import estimate_categorical_mu

    gamma = np.zeros((200, 3))
    result = estimate_categorical_mu(gamma, _two_level(3), init_lambda=0.5)

    assert result.warning is None
