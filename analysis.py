# custom commands: hazard detection + delay estimate

from minimize import covers, count_literals


# custom #1: static hazard detection
#
# static-1 hazard (SOP): 1 input changes, F should stay 1, but the 2 rows
# are covered by different terms -> 1 AND turns off before the other turns on
# -> F can glitch 1 -> 0 -> 1
#
# Ex: F = AB + A'C, B = 1, C = 1, A goes 0 -> 1
#   before: A'C holds F high    after: AB holds F high
#   in between neither term is 1 -> glitch
#   fix: add consensus term BC (stays 1 the whole time)
#
# same check on POS w/ OFF-set -> static-0 hazards (0 -> 1 -> 0)


# find neighbor rows (differ in 1 bit), both in care_set, no 1 term covers both
# SOP: pass ON-set, POS: pass OFF-set
# returns list of (row_a, row_b, variable_position)
# Ex: F = AB + A'C --> cover ["0-1", "11-"], ON-set [1, 3, 6, 7]
#     rows 3 (011) + 7 (111) differ only in A, no term covers both
#     --> [(3, 7, 0)]
def find_hazards(cover, care_set, n):
    hazards = []

    for row in care_set:
        for position in range(n):
            bit = 1 << (n - 1 - position)

            # only check from side where bit = 0 -> each pair checked once
            if (row & bit) == 0:
                partner = row | bit
                if partner in care_set and not covered_together(cover, row, partner):
                    hazards.append((row, partner, position))

    return hazards


# true if 1 term of the cover has both rows
def covered_together(cover, row_a, row_b):
    for term in cover:
        if covers(term, row_a) and covers(term, row_b):
            return True
    return False


# fix each hazard: add smallest prime implicant covering both rows (consensus term)
# returns (new_cover, added_terms)
# Ex: F = AB + A'C --> (["0-1", "11-", "-11"], ["-11"])     i.e. add BC
def fix_hazards(cover, primes, hazards):
    new_cover = list(cover)
    added = []

    for row_a, row_b, position in hazards:
        # already fixed by a term added earlier
        if covered_together(new_cover, row_a, row_b):
            continue

        best = None
        for prime in primes:
            if covers(prime, row_a) and covers(prime, row_b):
                if best is None or count_literals(prime) < count_literals(best):
                    best = prime

        new_cover.append(best)
        added.append(best)

    return new_cover, added


# hazard -> readable text
# Ex: (3, 7, 0) w/ variables [A, B, C] --> "A changes while B=1, C=1  (m3 <-> m7)"
def describe_hazard(hazard, variables):
    row_a, row_b, position = hazard
    n = len(variables)

    held = []
    for other in range(n):
        if other != position:
            bit = (row_a >> (n - 1 - other)) & 1
            held.append(f"{variables[other]}={bit}")

    text = f"{variables[position]} changes"
    if len(held) > 0:
        text = text + " while " + ", ".join(held)
    return text + f"  (m{row_a} <-> m{row_b})"


# custom #2: delay estimate
#
# every circuit has the same shape:
#   SOP:  inputs -> NOTs -> ANDs -> 1 OR  -> F
#   POS:  inputs -> NOTs -> ORs  -> 1 AND -> F
# path delay = sum of gates on it, circuit delay = slowest (critical) path
#
# units = gate delays (1 = 1 gate), swap in ns from a datasheet for real times
NOT_DELAY = 1.0
AND_DELAY = 1.0
OR_DELAY = 1.0


# gate count + delay of a 2-level circuit
# patterns: circuit terms (POS: implicants of F')
# is_pos:   False = SOP, True = POS
# returns (gate_count, delay)
# Ex: F = A'C + AB'  (SOP, patterns ["0-1", "10-"])
#     gates: NOT A, NOT B, AND, AND, OR = 5
#     slowest path: A -> NOT -> AND -> OR = 3.0
#     --> (5, 3.0)
def estimate_delay(patterns, is_pos):
    # constant output (F = 0 or 1) -> no gates
    if len(patterns) == 0:
        return 0, 0.0
    for pattern in patterns:
        if count_literals(pattern) == 0:
            return 0, 0.0

    # complemented literal: '0' in SOP, '1' in POS (DeMorgan)
    if is_pos:
        inverted = "1"
        first_level_delay = OR_DELAY
        second_level_delay = AND_DELAY
    else:
        inverted = "0"
        first_level_delay = AND_DELAY
        second_level_delay = OR_DELAY

    n = len(patterns[0])
    gates = 0

    # 1 NOT per variable that shows up complemented
    for position in range(n):
        for pattern in patterns:
            if pattern[position] == inverted:
                gates = gates + 1
                break

    # 1 1st-level gate per term w/ 2+ literals (1 literal = just a wire)
    worst_term_delay = 0.0
    for pattern in patterns:
        term_delay = 0.0

        if inverted in pattern:
            term_delay = term_delay + NOT_DELAY

        if count_literals(pattern) >= 2:
            gates = gates + 1
            term_delay = term_delay + first_level_delay

        if term_delay > worst_term_delay:
            worst_term_delay = term_delay

    # output gate if 2+ terms
    delay = worst_term_delay
    if len(patterns) >= 2:
        gates = gates + 1
        delay = delay + second_level_delay

    return gates, delay
