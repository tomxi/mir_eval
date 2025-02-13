"""
Pattern discovery involves the identification of musical patterns (i.e. short
fragments or melodic ideas that repeat at least twice) both from audio and
symbolic representations.  The metrics used to evaluate pattern discovery
systems attempt to quantify the ability of the algorithm to not only determine
the present patterns in a piece, but also to find all of their occurrences.

Based on the methods described here:
    T. Collins. MIREX task: Discovery of repeated themes & sections.
    http://www.music-ir.org/mirex/wiki/2013:Discovery_of_Repeated_Themes_&_Sections,
    2013.

Conventions
-----------

The input format can be automatically generated by calling
:func:`mir_eval.io.load_patterns`.  This format is a list of a list of
tuples.  The first list collections patterns, each of which is a list of
occurrences, and each occurrence is a list of MIDI onset tuples of
``(onset_time, mid_note)``

A pattern is a list of occurrences. The first occurrence must be the prototype
of that pattern (i.e. the most representative of all the occurrences).  An
occurrence is a list of tuples containing the onset time and the midi note
number.

Metrics
-------

* :func:`mir_eval.pattern.standard_FPR`: Strict metric in order to find the
  possibly transposed patterns of exact length. This is the only metric that
  considers transposed patterns.
* :func:`mir_eval.pattern.establishment_FPR`: Evaluates the amount of patterns
  that were successfully identified by the estimated results, no matter how
  many occurrences they found.  In other words, this metric captures how the
  algorithm successfully *established* that a pattern repeated at least twice,
  and this pattern is also found in the reference annotation.
* :func:`mir_eval.pattern.occurrence_FPR`: Evaluation of how well an estimation
  can effectively identify all the occurrences of the found patterns,
  independently of how many patterns have been discovered. This metric has a
  threshold parameter that indicates how similar two occurrences must be in
  order to be considered equal.  In MIREX, this evaluation is run twice, with
  thresholds .75 and .5.
* :func:`mir_eval.pattern.three_layer_FPR`: Aims to evaluate the general
  similarity between the reference and the estimations, combining both the
  establishment of patterns and the retrieval of its occurrences in a single F1
  score.
* :func:`mir_eval.pattern.first_n_three_layer_P`: Computes the three-layer
  precision for the first N patterns only in order to measure the ability of
  the algorithm to sort the identified patterns based on their relevance.
* :func:`mir_eval.pattern.first_n_target_proportion_R`: Computes the target
  proportion recall for the first N patterns only in order to measure the
  ability of the algorithm to sort the identified patterns based on their
  relevance.
"""

import numpy as np
from . import util
import warnings
import collections


def _n_onset_midi(patterns):
    """Compute the number of onset_midi objects in a pattern

    Parameters
    ----------
    patterns
        A list of patterns using the format returned by
        :func:`mir_eval.io.load_patterns()`

    Returns
    -------
    n_onsets : int
        Number of onsets within the pattern.

    """
    return len([o_m for pat in patterns for occ in pat for o_m in occ])


def validate(reference_patterns, estimated_patterns):
    """Check that the input annotations to a metric look like valid pattern
    lists, and throws helpful errors if not.

    Parameters
    ----------
    reference_patterns : list
        The reference patterns using the format returned by
        :func:`mir_eval.io.load_patterns()`
    estimated_patterns : list
        The estimated patterns in the same format
    """
    # Warn if pattern lists are empty
    if _n_onset_midi(reference_patterns) == 0:
        warnings.warn("Reference patterns are empty.")
    if _n_onset_midi(estimated_patterns) == 0:
        warnings.warn("Estimated patterns are empty.")
    for patterns in [reference_patterns, estimated_patterns]:
        for pattern in patterns:
            if len(pattern) <= 0:
                raise ValueError(
                    "Each pattern must contain at least one " "occurrence."
                )
            for occurrence in pattern:
                for onset_midi in occurrence:
                    if len(onset_midi) != 2:
                        raise ValueError(
                            "The (onset, midi) tuple must "
                            "contain exactly 2 elements."
                        )


def _occurrence_intersection(occ_P, occ_Q):
    """Compute the intersection between two occurrences.

    Parameters
    ----------
    occ_P : list of tuples
        (onset, midi) pairs representing the reference occurrence.
    occ_Q : list
        second list of (onset, midi) tuples

    Returns
    -------
    S : set
        Set of the intersection between occ_P and occ_Q.

    """
    set_P = {tuple(onset_midi) for onset_midi in occ_P}
    set_Q = {tuple(onset_midi) for onset_midi in occ_Q}
    return set_P & set_Q  # Return the intersection


def _compute_score_matrix(P, Q, similarity_metric="cardinality_score"):
    """Compute the score matrix between the patterns P and Q.

    Parameters
    ----------
    P : list
        Pattern containing a list of occurrences.
    Q : list
        Pattern containing a list of occurrences.
    similarity_metric : str
        A string representing the metric to be used
        when computing the similarity matrix. Accepted values:
        - "cardinality_score":
            Count of the intersection between occurrences.
        (Default value = "cardinality_score")

    Returns
    -------
    sm : np.array
        The score matrix between P and Q using the similarity_metric.

    """
    sm = np.zeros((len(P), len(Q)))  # The score matrix
    for iP, occ_P in enumerate(P):
        for iQ, occ_Q in enumerate(Q):
            if similarity_metric == "cardinality_score":
                denom = float(np.max([len(occ_P), len(occ_Q)]))
                # Compute the score
                sm[iP, iQ] = len(_occurrence_intersection(occ_P, occ_Q)) / denom
            # TODO: More scores: 'normalised matching socre'
            else:
                raise ValueError(
                    "The similarity metric (%s) can only be: " "'cardinality_score'."
                )
    return sm


def standard_FPR(reference_patterns, estimated_patterns, tol=1e-5):
    """Compute the standard F1 Score, Precision and Recall.

    This metric checks if the prototype patterns of the reference match
    possible translated patterns in the prototype patterns of the estimations.
    Since the sizes of these prototypes must be equal, this metric is quite
    restrictive and it tends to be 0 in most of 2013 MIREX results.

    Examples
    --------
    >>> ref_patterns = mir_eval.io.load_patterns("ref_pattern.txt")
    >>> est_patterns = mir_eval.io.load_patterns("est_pattern.txt")
    >>> F, P, R = mir_eval.pattern.standard_FPR(ref_patterns, est_patterns)

    Parameters
    ----------
    reference_patterns : list
        The reference patterns using the format returned by
        :func:`mir_eval.io.load_patterns()`
    estimated_patterns : list
        The estimated patterns in the same format
    tol : float
        Tolerance level when comparing reference against estimation.
        Default parameter is the one found in the original matlab code by
        Tom Collins used for MIREX 2013.
        (Default value = 1e-5)

    Returns
    -------
    f_measure : float
        The standard F1 Score
    precision : float
        The standard Precision
    recall : float
        The standard Recall

    """
    validate(reference_patterns, estimated_patterns)
    nP = len(reference_patterns)  # Number of patterns in the reference
    nQ = len(estimated_patterns)  # Number of patterns in the estimation
    k = 0  # Number of patterns that match

    # If no patterns were provided, metric is zero
    if _n_onset_midi(reference_patterns) == 0 or _n_onset_midi(estimated_patterns) == 0:
        return 0.0, 0.0, 0.0

    # Find matches of the prototype patterns
    for ref_pattern in reference_patterns:
        P = np.asarray(ref_pattern[0])  # Get reference prototype
        for est_pattern in estimated_patterns:
            Q = np.asarray(est_pattern[0])  # Get estimation prototype

            if len(P) != len(Q):
                continue

            # Check transposition given a certain tolerance
            if len(P) == len(Q) == 1 or np.max(np.abs(np.diff(P - Q, axis=0))) < tol:
                k += 1
                break

    # Compute the standard measures
    precision = k / float(nQ)
    recall = k / float(nP)
    f_measure = util.f_measure(precision, recall)
    return f_measure, precision, recall


def establishment_FPR(
    reference_patterns, estimated_patterns, similarity_metric="cardinality_score"
):
    """Compute the establishment F1 Score, Precision and Recall.

    Examples
    --------
    >>> ref_patterns = mir_eval.io.load_patterns("ref_pattern.txt")
    >>> est_patterns = mir_eval.io.load_patterns("est_pattern.txt")
    >>> F, P, R = mir_eval.pattern.establishment_FPR(ref_patterns,
    ...                                              est_patterns)

    Parameters
    ----------
    reference_patterns : list
        The reference patterns in the format returned by
        :func:`mir_eval.io.load_patterns()`

    estimated_patterns : list
        The estimated patterns in the same format

    similarity_metric : str
        A string representing the metric to be used when computing the
        similarity matrix. Accepted values:

            - "cardinality_score": Count of the intersection
              between occurrences.

        (Default value = "cardinality_score")

    Returns
    -------
    f_measure : float
        The establishment F1 Score
    precision : float
        The establishment Precision
    recall : float
        The establishment Recall

    """
    validate(reference_patterns, estimated_patterns)
    nP = len(reference_patterns)  # Number of elements in reference
    nQ = len(estimated_patterns)  # Number of elements in estimation
    S = np.zeros((nP, nQ))  # Establishment matrix

    # If no patterns were provided, metric is zero
    if _n_onset_midi(reference_patterns) == 0 or _n_onset_midi(estimated_patterns) == 0:
        return 0.0, 0.0, 0.0

    for iP, ref_pattern in enumerate(reference_patterns):
        for iQ, est_pattern in enumerate(estimated_patterns):
            s = _compute_score_matrix(ref_pattern, est_pattern, similarity_metric)
            S[iP, iQ] = np.max(s)

    # Compute scores
    precision = np.mean(np.max(S, axis=0))
    recall = np.mean(np.max(S, axis=1))
    f_measure = util.f_measure(precision, recall)
    return f_measure, precision, recall


def occurrence_FPR(
    reference_patterns,
    estimated_patterns,
    thres=0.75,
    similarity_metric="cardinality_score",
):
    """Compute the occurrence F1 Score, Precision and Recall.

    Examples
    --------
    >>> ref_patterns = mir_eval.io.load_patterns("ref_pattern.txt")
    >>> est_patterns = mir_eval.io.load_patterns("est_pattern.txt")
    >>> F, P, R = mir_eval.pattern.occurrence_FPR(ref_patterns,
    ...                                           est_patterns)

    Parameters
    ----------
    reference_patterns : list
        The reference patterns in the format returned by
        :func:`mir_eval.io.load_patterns()`

    estimated_patterns : list
        The estimated patterns in the same format

    thres : float
        How similar two occurrences must be in order to be considered
        equal
        (Default value = .75)

    similarity_metric : str
        A string representing the metric to be used
        when computing the similarity matrix. Accepted values:

            - "cardinality_score": Count of the intersection
              between occurrences.

        (Default value = "cardinality_score")

    Returns
    -------
    f_measure : float
        The occurrence F1 Score
    precision : float
        The occurrence Precision
    recall : float
        The occurrence Recall
    """
    validate(reference_patterns, estimated_patterns)
    # Number of elements in reference
    nP = len(reference_patterns)
    # Number of elements in estimation
    nQ = len(estimated_patterns)
    # Occurrence matrix with Precision and recall in its last dimension
    O_PR = np.zeros((nP, nQ, 2))

    # Index of the values that are greater than the specified threshold
    rel_idx = np.empty((0, 2), dtype=int)

    # If no patterns were provided, metric is zero
    if _n_onset_midi(reference_patterns) == 0 or _n_onset_midi(estimated_patterns) == 0:
        return 0.0, 0.0, 0.0

    for iP, ref_pattern in enumerate(reference_patterns):
        for iQ, est_pattern in enumerate(estimated_patterns):
            s = _compute_score_matrix(ref_pattern, est_pattern, similarity_metric)
            if np.max(s) >= thres:
                O_PR[iP, iQ, 0] = np.mean(np.max(s, axis=0))
                O_PR[iP, iQ, 1] = np.mean(np.max(s, axis=1))
                rel_idx = np.vstack((rel_idx, [iP, iQ]))

    # Compute the scores
    if len(rel_idx) == 0:
        precision = 0
        recall = 0
    else:
        P = O_PR[:, :, 0]
        precision = np.mean(np.max(P[np.ix_(rel_idx[:, 0], rel_idx[:, 1])], axis=0))
        R = O_PR[:, :, 1]
        recall = np.mean(np.max(R[np.ix_(rel_idx[:, 0], rel_idx[:, 1])], axis=1))
    f_measure = util.f_measure(precision, recall)
    return f_measure, precision, recall


def three_layer_FPR(reference_patterns, estimated_patterns):
    """Three Layer F1 Score, Precision and Recall. As described by Meridith.

    Examples
    --------
    >>> ref_patterns = mir_eval.io.load_patterns("ref_pattern.txt")
    >>> est_patterns = mir_eval.io.load_patterns("est_pattern.txt")
    >>> F, P, R = mir_eval.pattern.three_layer_FPR(ref_patterns,
    ...                                            est_patterns)

    Parameters
    ----------
    reference_patterns : list
        The reference patterns in the format returned by
        :func:`mir_eval.io.load_patterns()`
    estimated_patterns : list
        The estimated patterns in the same format

    Returns
    -------
    f_measure : float
        The three-layer F1 Score
    precision : float
        The three-layer Precision
    recall : float
        The three-layer Recall

    """
    validate(reference_patterns, estimated_patterns)

    def compute_first_layer_PR(ref_occs, est_occs):
        """Compute the first layer Precision and Recall values given the
        set of occurrences in the reference and the set of occurrences in the
        estimation.

        Parameters
        ----------
        ref_occs
        est_occs

        Returns
        -------
        precision
        recall
        """
        # Find the length of the intersection between reference and estimation
        s = len(_occurrence_intersection(ref_occs, est_occs))

        # Compute the first layer scores
        precision = s / float(len(ref_occs))
        recall = s / float(len(est_occs))
        return precision, recall

    def compute_second_layer_PR(ref_pattern, est_pattern):
        """Compute the second layer Precision and Recall values given the
        set of occurrences in the reference and the set of occurrences in the
        estimation.

        Parameters
        ----------
        ref_pattern
        est_pattern

        Returns
        -------
        precision
        recall
        """
        # Compute the first layer scores
        F_1 = compute_layer(ref_pattern, est_pattern)

        # Compute the second layer scores
        precision = np.mean(np.max(F_1, axis=0))
        recall = np.mean(np.max(F_1, axis=1))
        return precision, recall

    def compute_layer(ref_elements, est_elements, layer=1):
        """Compute the F-measure matrix for a given layer. The reference and
        estimated elements can be either patterns or occurrences, depending
        on the layer.

        For layer 1, the elements must be occurrences.
        For layer 2, the elements must be patterns.

        Parameters
        ----------
        ref_elements
        est_elements
        layer
            (Default value = 1)

        Returns
        -------
        F : F-measure for the given layer
        """
        if layer != 1 and layer != 2:
            raise ValueError("Layer (%d) must be an integer between 1 and 2" % layer)

        nP = len(ref_elements)  # Number of elements in reference
        nQ = len(est_elements)  # Number of elements in estimation
        F = np.zeros((nP, nQ))  # F-measure matrix for the given layer
        for iP in range(nP):
            for iQ in range(nQ):
                if layer == 1:
                    func = compute_first_layer_PR
                elif layer == 2:
                    func = compute_second_layer_PR

                # Compute layer scores
                precision, recall = func(ref_elements[iP], est_elements[iQ])
                F[iP, iQ] = util.f_measure(precision, recall)
        return F

    # If no patterns were provided, metric is zero
    if _n_onset_midi(reference_patterns) == 0 or _n_onset_midi(estimated_patterns) == 0:
        return 0.0, 0.0, 0.0

    # Compute the second layer (it includes the first layer)
    F_2 = compute_layer(reference_patterns, estimated_patterns, layer=2)

    # Compute the final scores (third layer)
    precision_3 = np.mean(np.max(F_2, axis=0))
    recall_3 = np.mean(np.max(F_2, axis=1))
    f_measure_3 = util.f_measure(precision_3, recall_3)
    return f_measure_3, precision_3, recall_3


def first_n_three_layer_P(reference_patterns, estimated_patterns, n=5):
    """First n three-layer precision.

    This metric is basically the same as the three-layer FPR but it is only
    applied to the first n estimated patterns, and it only returns the
    precision. In MIREX and typically, n = 5.

    Examples
    --------
    >>> ref_patterns = mir_eval.io.load_patterns("ref_pattern.txt")
    >>> est_patterns = mir_eval.io.load_patterns("est_pattern.txt")
    >>> P = mir_eval.pattern.first_n_three_layer_P(ref_patterns,
    ...                                            est_patterns, n=5)

    Parameters
    ----------
    reference_patterns : list
        The reference patterns in the format returned by
        :func:`mir_eval.io.load_patterns()`
    estimated_patterns : list
        The estimated patterns in the same format
    n : int
        Number of patterns to consider from the estimated results, in
        the order they appear in the matrix
        (Default value = 5)

    Returns
    -------
    precision : float
        The first n three-layer Precision
    """
    validate(reference_patterns, estimated_patterns)
    # If no patterns were provided, metric is zero
    if _n_onset_midi(reference_patterns) == 0 or _n_onset_midi(estimated_patterns) == 0:
        return 0.0, 0.0, 0.0

    # Get only the first n patterns from the estimated results
    fn_est_patterns = estimated_patterns[: min(len(estimated_patterns), n)]

    # Compute the three-layer scores for the first n estimated patterns
    F, P, R = three_layer_FPR(reference_patterns, fn_est_patterns)

    return P  # Return the precision only


def first_n_target_proportion_R(reference_patterns, estimated_patterns, n=5):
    """First n target proportion establishment recall metric.

    This metric is similar is similar to the establishment FPR score, but it
    only takes into account the first n estimated patterns and it only
    outputs the Recall value of it.

    Examples
    --------
    >>> ref_patterns = mir_eval.io.load_patterns("ref_pattern.txt")
    >>> est_patterns = mir_eval.io.load_patterns("est_pattern.txt")
    >>> R = mir_eval.pattern.first_n_target_proportion_R(
    ...                                 ref_patterns, est_patterns, n=5)

    Parameters
    ----------
    reference_patterns : list
        The reference patterns in the format returned by
        :func:`mir_eval.io.load_patterns()`
    estimated_patterns : list
        The estimated patterns in the same format
    n : int
        Number of patterns to consider from the estimated results, in
        the order they appear in the matrix.
        (Default value = 5)

    Returns
    -------
    recall : float
        The first n target proportion Recall.
    """
    validate(reference_patterns, estimated_patterns)
    # If no patterns were provided, metric is zero
    if _n_onset_midi(reference_patterns) == 0 or _n_onset_midi(estimated_patterns) == 0:
        return 0.0, 0.0, 0.0

    # Get only the first n patterns from the estimated results
    fn_est_patterns = estimated_patterns[: min(len(estimated_patterns), n)]

    F, P, R = establishment_FPR(reference_patterns, fn_est_patterns)
    return R


def evaluate(ref_patterns, est_patterns, **kwargs):
    """Load data and perform the evaluation.

    Examples
    --------
    >>> ref_patterns = mir_eval.io.load_patterns("ref_pattern.txt")
    >>> est_patterns = mir_eval.io.load_patterns("est_pattern.txt")
    >>> scores = mir_eval.pattern.evaluate(ref_patterns, est_patterns)

    Parameters
    ----------
    ref_patterns : list
        The reference patterns in the format returned by
        :func:`mir_eval.io.load_patterns()`
    est_patterns : list
        The estimated patterns in the same format
    **kwargs
        Additional keyword arguments which will be passed to the
        appropriate metric or preprocessing functions.

    Returns
    -------
    scores : dict
        Dictionary of scores, where the key is the metric name (str) and
        the value is the (float) score achieved.
    """
    # Compute all the metrics
    scores = collections.OrderedDict()

    # Standard scores
    scores["F"], scores["P"], scores["R"] = util.filter_kwargs(
        standard_FPR, ref_patterns, est_patterns, **kwargs
    )

    # Establishment scores
    scores["F_est"], scores["P_est"], scores["R_est"] = util.filter_kwargs(
        establishment_FPR, ref_patterns, est_patterns, **kwargs
    )

    # Occurrence scores
    # Force these values for thresh
    kwargs["thresh"] = 0.5
    scores["F_occ.5"], scores["P_occ.5"], scores["R_occ.5"] = util.filter_kwargs(
        occurrence_FPR, ref_patterns, est_patterns, **kwargs
    )
    kwargs["thresh"] = 0.75
    scores["F_occ.75"], scores["P_occ.75"], scores["R_occ.75"] = util.filter_kwargs(
        occurrence_FPR, ref_patterns, est_patterns, **kwargs
    )

    # Three-layer scores
    scores["F_3"], scores["P_3"], scores["R_3"] = util.filter_kwargs(
        three_layer_FPR, ref_patterns, est_patterns, **kwargs
    )

    # First Five Patterns scores
    # Set default value of n
    if "n" not in kwargs:
        kwargs["n"] = 5
    scores["FFP"] = util.filter_kwargs(
        first_n_three_layer_P, ref_patterns, est_patterns, **kwargs
    )
    scores["FFTP_est"] = util.filter_kwargs(
        first_n_target_proportion_R, ref_patterns, est_patterns, **kwargs
    )

    return scores
