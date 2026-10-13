"""The pure helpers the timeline uses to edit the parts: text <-> ranges, add / move / remove / skip / isolate."""

import random

import pytest

from luckytwitch_engine import (
    MIN_PART,
    Edge,
    PlanError,
    add_cut,
    edges_of,
    isolate_span,
    move_edge,
    nearest_edge,
    parse_cut_points,
    part_index_at,
    ranges_of,
    ranges_to_text,
    remove_cut,
    toggle_part,
)

DUR = 7200.0


# --------------------------------------------------------------------------- text <-> ranges
def test_ranges_of_reads_the_cut_text_in_whole_seconds():
    assert ranges_of("0:00:00 - 30:00 - end", DUR) == [(0, 1800), (1800, 7200)]
    assert ranges_of("0:00 - 10:00 ; 1:00:00 - 1:30:00", DUR) == [(0, 600), (3600, 5400)]
    assert ranges_of("0:00 - 1h", DUR) == [(0, 3600)]


def test_ranges_of_rounds_fractions_and_drops_parts_that_vanish():
    assert ranges_of("10.4 - 20.6", DUR) == [(10, 21)]
    assert ranges_of("10.1 - 10.4 ; 50 - 60", DUR) == [(50, 60)]


def test_ranges_of_passes_errors_on():
    with pytest.raises(PlanError):
        ranges_of("30:00 - 10:00", DUR)
    with pytest.raises(PlanError):
        ranges_of("", DUR)


def test_touching_parts_share_a_line_and_skipped_sections_start_a_new_one():
    assert ranges_to_text([(0, 1800), (1800, 7200)], DUR) == "0:00:00 - 0:30:00 - end"
    assert ranges_to_text([(0, 600), (3600, 5400)], DUR) == "0:00:00 - 0:10:00\n1:00:00 - 1:30:00"
    assert ranges_to_text([(0, 600), (600, 1200), (3600, 7200)], DUR) == "0:00:00 - 0:10:00 - 0:20:00\n1:00:00 - end"


def test_end_is_only_written_for_the_last_boundary_and_only_near_the_vod_end():
    assert ranges_to_text([(0, 7200)], DUR) == "0:00:00 - end"
    assert ranges_to_text([(0, 7199)], DUR) == "0:00:00 - 1:59:59"
    assert ranges_to_text([(0, 3600)], None) == "0:00:00 - 1:00:00"
    assert ranges_to_text([(0, 7200)], None) == "0:00:00 - 2:00:00"


def test_text_and_ranges_round_trip():
    for text in ("0:00:00 - end", "0:00:00 - 0:30:00 - end", "0:10:00 - 0:20:00\n1:00:00 - 1:30:00 - end"):
        assert ranges_to_text(ranges_of(text, DUR), DUR) == text


# --------------------------------------------------------------------------- edges
def test_edges_distinguish_shared_cuts_from_the_borders_of_skipped_sections():
    ranges = [(0, 600), (600, 1200), (3600, 5400)]
    assert edges_of(ranges) == [
        Edge("start", 0, 0), Edge("cut", 0, 600), Edge("end", 1, 1200), Edge("start", 2, 3600), Edge("end", 2, 5400),
    ]


def test_nearest_edge_respects_the_tolerance():
    ranges = [(0, 600), (600, 1200)]
    assert nearest_edge(ranges, 603, 5) == Edge("cut", 0, 600)
    assert nearest_edge(ranges, 610, 5) is None
    assert nearest_edge([], 5, 5) is None


def test_part_index_at():
    ranges = [(0, 600), (3600, 5400)]
    assert part_index_at(ranges, 0) == 0 and part_index_at(ranges, 599.9) == 0
    assert part_index_at(ranges, 600) is None and part_index_at(ranges, 4000) == 1
    assert part_index_at(ranges, 5400) is None


# --------------------------------------------------------------------------- add_cut
def test_add_cut_splits_the_part_that_contains_the_time():
    assert add_cut([(0, 7200)], 1800) == [(0, 1800), (1800, 7200)]
    assert add_cut([(0, 600), (3600, 5400)], 4000.4) == [(0, 600), (3600, 4000), (4000, 5400)]


def test_add_cut_does_nothing_on_an_edge_near_an_edge_or_in_a_skipped_section():
    ranges = [(0, 600), (3600, 5400)]
    assert add_cut(ranges, 600) is None  # on the edge
    assert add_cut(ranges, 0) is None
    assert add_cut(ranges, 3600.4) is None  # rounds onto the start
    assert add_cut(ranges, 1000) is None  # skipped section
    assert add_cut(ranges, 9999) is None  # beyond everything
    assert add_cut([(0, 600)], 599.6) is None  # rounds to the end


def test_add_cut_never_makes_a_part_shorter_than_the_minimum():
    assert add_cut([(0, 600)], 1) == [(0, 1), (1, 600)]
    assert add_cut([(0, 600)], 599) == [(0, 599), (599, 600)]
    assert MIN_PART == 1.0


def test_adding_the_same_cut_twice_changes_nothing():
    once = add_cut([(0, 7200)], 3597)
    assert add_cut(once, 3597) is None


# --------------------------------------------------------------------------- move_edge
def test_moving_a_shared_cut_moves_both_neighbours():
    assert move_edge([(0, 600), (600, 1200)], Edge("cut", 0, 600), 900.2, DUR) == [(0, 900), (900, 1200)]


def test_a_cut_cannot_cross_its_neighbours_ends():
    r = [(100, 600), (600, 1200)]
    assert move_edge(r, Edge("cut", 0, 600), 5, DUR) == [(100, 101), (101, 1200)]
    assert move_edge(r, Edge("cut", 0, 600), 5000, DUR) == [(100, 1199), (1199, 1200)]


def test_a_free_start_can_move_into_the_skipped_section_but_not_into_the_previous_part():
    r = [(0, 600), (3600, 5400)]
    edge = Edge("start", 1, 3600)
    assert move_edge(r, edge, 2000, DUR) == [(0, 600), (2000, 5400)]
    assert move_edge(r, edge, 100, DUR) == [(0, 600), (600, 5400)]  # stops where the previous part ends
    assert move_edge(r, edge, 9000, DUR) == [(0, 600), (5399, 5400)]


def test_a_free_end_can_move_into_the_skipped_section_and_to_the_vod_end():
    r = [(0, 600), (3600, 5400)]
    assert move_edge(r, Edge("end", 0, 600), 2000, DUR) == [(0, 2000), (3600, 5400)]
    assert move_edge(r, Edge("end", 0, 600), 9000, DUR) == [(0, 3600), (3600, 5400)]
    assert move_edge(r, Edge("end", 1, 5400), 99999, DUR) == [(0, 600), (3600, 7200)]
    assert move_edge(r, Edge("end", 1, 5400), -5, DUR) == [(0, 600), (3600, 3601)]


def test_the_first_start_cannot_go_below_zero():
    assert move_edge([(100, 600)], Edge("start", 0, 100), -50, DUR) == [(0, 600)]


# --------------------------------------------------------------------------- remove_cut / toggle_part
def test_remove_cut_merges_the_two_parts():
    assert remove_cut([(0, 600), (600, 1200), (3600, 5400)], 0) == [(0, 1200), (3600, 5400)]
    assert remove_cut([(0, 600), (600, 1200)], 0) == [(0, 1200)]


def test_clicking_a_part_skips_it_and_clicking_the_gap_brings_it_back():
    r = [(0, 600), (600, 1200), (1200, 7200)]
    skipped = toggle_part(r, 900, DUR)
    assert skipped == [(0, 600), (1200, 7200)]
    assert toggle_part(skipped, 900, DUR) == r  # same split points as before


def test_toggling_a_leading_or_trailing_gap():
    assert toggle_part([(600, 1200)], 100, DUR) == [(0, 600), (600, 1200)]
    assert toggle_part([(600, 1200)], 5000, DUR) == [(600, 1200), (1200, 7200)]


def test_the_last_remaining_part_cannot_be_skipped():
    assert toggle_part([(0, 7200)], 100, DUR) is None


def test_a_gap_smaller_than_the_minimum_cannot_be_filled():
    assert toggle_part([(0, 600), (600, 1200)], 1200, 1200) is None  # nothing left after the last part


# --------------------------------------------------------------------------- isolate_span
def test_isolating_a_span_inside_one_part_gives_three_parts():
    assert isolate_span([(0, 7200)], 1000, 2000, DUR) == [(0, 1000), (1000, 2000), (2000, 7200)]


def test_isolating_a_span_brings_back_skipped_sections_inside_it():
    r = [(0, 1500), (3000, 7200)]
    assert isolate_span(r, 1000, 4000, DUR) == [(0, 1000), (1000, 1500), (1500, 3000), (3000, 4000), (4000, 7200)]


def test_isolating_a_span_that_starts_on_an_existing_cut_adds_no_extra_cut():
    assert isolate_span([(0, 1000), (1000, 7200)], 1000, 2000, DUR) == [(0, 1000), (1000, 2000), (2000, 7200)]


def test_isolating_with_only_keeps_just_that_span():
    assert isolate_span([(0, 1000), (3000, 7200)], 500, 4000, DUR, only=True) == [(500, 4000)]


def test_isolating_is_clamped_to_the_vod_and_ignores_empty_spans():
    assert isolate_span([(0, 7200)], 7000, 9000, DUR) == [(0, 7000), (7000, 7200)]
    assert isolate_span([(0, 7200)], 1000, 1000, DUR) == [(0, 7200)]
    assert isolate_span([(0, 7200)], -50, 100, DUR, only=True) == [(0, 100)]


# --------------------------------------------------------------------------- random sequences of edits
def check_valid(ranges, duration):
    assert ranges, "an edit emptied the plan"
    prev_end = 0
    for s, e in ranges:
        assert s == int(s) and e == int(e)
        assert prev_end <= s and e - s >= MIN_PART and e <= duration
        prev_end = e
    text = ranges_to_text(ranges, duration)
    assert ranges_of(text, duration) == ranges  # what the timeline shows is what the planner reads
    assert [(p.start, p.end) for p in parse_cut_points(text, duration)] == ranges


@pytest.mark.parametrize("seed", range(40))
def test_any_sequence_of_edits_leaves_a_valid_plan(seed):
    rng = random.Random(seed)
    duration = rng.choice([30, 600, 7200.0, 26264])
    ranges = [(0, int(duration))]
    for _ in range(60):
        t = rng.uniform(-10, duration + 10)
        op = rng.choice(["add", "move", "remove", "toggle", "isolate", "only"])
        if op == "add":
            ranges = add_cut(ranges, t) or ranges
        elif op == "move":
            edges = edges_of(ranges)
            ranges = move_edge(ranges, rng.choice(edges), t, duration)
        elif op == "remove":
            cuts = [e for e in edges_of(ranges) if e.kind == "cut"]
            if cuts:
                ranges = remove_cut(ranges, rng.choice(cuts).index)
        elif op == "toggle":
            ranges = toggle_part(ranges, t, duration) or ranges
        else:
            ranges = isolate_span(ranges, t, t + rng.uniform(0, duration / 3), duration, only=(op == "only"))
        check_valid(ranges, duration)
