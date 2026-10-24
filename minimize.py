# 2-level minimization (Quine-McCluskey)
#
# implicant = pattern string, 1 char per variable:
#   '1' --> plain        (A)
#   '0' --> complemented (A')
#   '-' --> not in term
# Ex: variables [A, B, C]
#   "011" --> A'BC   (1 minterm, m3)
#   "1-0" --> AC'    (covers m4 = 100, m6 = 110)
#   "---" --> 1      (covers everything)

from itertools import combinations

from parser import to_bits

# max non-essential PIs to brute force, above this -> greedy (faster, maybe not minimal)
EXACT_SEARCH_LIMIT = 16


# does implicant cover minterm?
# Ex:
# covers("1-0", 4) --> True   (4 = 100)
# covers("1-0", 5) --> False  (5 = 101, last bit off)
def covers(pattern, minterm):
    bits = to_bits(minterm, len(pattern))
    for position in range(len(pattern)):
        if pattern[position] != "-" and pattern[position] != bits[position]:
            return False
    return True


# literal count = chars that aren't '-'
# Ex: count_literals("1-0") --> 2
def count_literals(pattern):
    count = 0
    for character in pattern:
        if character != "-":
            count = count + 1
    return count


# sort: fewest literals 1st, then alphabetical
# Ex: ["1-0", "--1", "011"] --> ["--1", "1-0", "011"]
def sort_implicants(patterns):
    def sort_key(pattern):
        return (count_literals(pattern), pattern)
    patterns.sort(key=sort_key)
    return patterns


# merge 2 implicants that differ in exactly 1 bit, that bit -> '-'
# Ex:
# combine("100", "110") --> "1-0"
# combine("1-0", "0-0") --> "--0"
# combine("100", "011") --> None (2+ bits differ)
# combine("1-0", "10-") --> None ('-' in diff spots)
def combine(a, b):
    merged = ""
    differences = 0

    for position in range(len(a)):
        if a[position] == b[position]:
            merged = merged + a[position]
        elif a[position] != "-" and b[position] != "-":
            differences = differences + 1
            merged = merged + "-"
        else:
            return None

    if differences == 1:
        return merged
    return None


# QM step 1: all prime implicants
# start w/ minterms, merge pairs each round until nothing merges
# anything that didn't merge in a round = prime
# Ex: minterms [1, 3, 4, 5], 3 variables
#   round 1: 001 011 100 101
#   round 2: 0-1 (1+3)  -01 (1+5)  10- (4+5)
#   round 3: nothing merges
#   --> ["-01", "0-1", "10-"]
def find_prime_implicants(minterms, n):
    current = []
    for minterm in minterms:
        current.append(to_bits(minterm, n))

    primes = []

    while len(current) > 0:
        merged = []        # bigger implicants made this round
        used = []          # ones from this round that merged

        for i in range(len(current)):
            for j in range(i + 1, len(current)):
                new_implicant = combine(current[i], current[j])
                if new_implicant is not None:
                    if new_implicant not in merged:
                        merged.append(new_implicant)
                    if current[i] not in used:
                        used.append(current[i])
                    if current[j] not in used:
                        used.append(current[j])

        # didn't merge -> can't get bigger -> prime
        for implicant in current:
            if implicant not in used and implicant not in primes:
                primes.append(implicant)

        current = merged

    return sort_implicants(primes)


# QM step 2: essential PIs = only PI covering some minterm
# Ex: primes ["-01", "0-1", "10-"], minterms [1, 3, 4, 5]
#   m3 only in 0-1, m4 only in 10-
#   --> ["0-1", "10-"]
def find_essential_implicants(primes, minterms):
    essentials = []

    for minterm in minterms:
        covering = []
        for prime in primes:
            if covers(prime, minterm):
                covering.append(prime)

        if len(covering) == 1 and covering[0] not in essentials:
            essentials.append(covering[0])

    return sort_implicants(essentials)


# true if every minterm covered by at least 1 implicant
def covers_all(implicants, minterms):
    for minterm in minterms:
        covered = False
        for implicant in implicants:
            if covers(implicant, minterm):
                covered = True
                break
        if not covered:
            return False
    return True


# QM step 3: smallest set of PIs
#   1. take essential PIs
#   2. leftover minterms: try every combo of other PIs, 1 at a time, then 2, ...
#      1st size that works = fewest terms, ties -> fewest literals
#   3. too many to try -> greedy (may not be minimal)
# returns (cover, exact)    exact = False if greedy used
# Ex: primes ["-01", "0-1", "10-"], essentials ["0-1", "10-"], minterms [1, 3, 4, 5]
#     essentials already cover everything --> (["0-1", "10-"], True)
def find_minimum_cover(primes, essentials, minterms):
    cover = list(essentials)

    # minterms essentials miss
    remaining = []
    for minterm in minterms:
        if not covers_all(cover, [minterm]):
            remaining.append(minterm)

    if len(remaining) == 0:
        return sort_implicants(cover), True

    # PIs that cover at least 1 leftover minterm
    candidates = []
    for prime in primes:
        if prime not in essentials:
            for minterm in remaining:
                if covers(prime, minterm):
                    candidates.append(prime)
                    break

    if len(candidates) <= EXACT_SEARCH_LIMIT:
        best = None
        best_literals = 0

        for size in range(1, len(candidates) + 1):
            # combinations(list, 2) = every pair, (list, 3) = every triple, ...
            for group in combinations(candidates, size):
                if covers_all(group, remaining):
                    literals = 0
                    for implicant in group:
                        literals = literals + count_literals(implicant)
                    if best is None or literals < best_literals:
                        best = group
                        best_literals = literals

            # found 1 at this size -> stop, bigger sizes = more terms
            if best is not None:
                break

        for implicant in best:
            cover.append(implicant)
        return sort_implicants(cover), True

    # greedy: keep taking PI that covers the most leftover minterms
    while len(remaining) > 0:
        best = None
        best_count = -1
        for candidate in candidates:
            count = 0
            for minterm in remaining:
                if covers(candidate, minterm):
                    count = count + 1
            if count > best_count:
                best = candidate
                best_count = count

        cover.append(best)

        still_remaining = []
        for minterm in remaining:
            if not covers(best, minterm):
                still_remaining.append(minterm)
        remaining = still_remaining

    return sort_implicants(cover), False


# patterns -> readable expressions

# implicant -> product term
# Ex: variables [A, B, C]
# "1-0" --> "AC'"
# "---" --> "1"
def product_term(pattern, variables):
    text = ""
    for position in range(len(pattern)):
        if pattern[position] == "1":
            text = text + variables[position]
        elif pattern[position] == "0":
            text = text + variables[position] + "'"

    if text == "":
        return "1"
    return text


# implicant of F' -> sum term of F (DeMorgan: (AC')' = A' + C)
# '1' -> complemented, '0' -> plain
# also how a maxterm is written: M4 = 100 --> (A' + B + C)
# Ex: variables [A, B, C]
# "1-0" --> "(A' + C)"
# "---" --> "0"
def sum_term(pattern, variables):
    literals = []
    for position in range(len(pattern)):
        if pattern[position] == "1":
            literals.append(variables[position] + "'")
        elif pattern[position] == "0":
            literals.append(variables[position])

    if len(literals) == 0:
        return "0"
    return "(" + " + ".join(literals) + ")"


# implicants -> SOP string
# Ex: ["0-1", "10-"] --> "A'C + AB'"
def sop_expression(patterns, variables):
    if len(patterns) == 0:
        return "0"
    terms = []
    for pattern in patterns:
        terms.append(product_term(pattern, variables))
    return " + ".join(terms)


# implicants of F' -> POS string of F
# Ex: ["1-0", "0-1"] --> "(A' + C)(A + C')"
def pos_expression(patterns, variables):
    if len(patterns) == 0:
        return "1"
    text = ""
    for pattern in patterns:
        text = text + sum_term(pattern, variables)
    return text


# row numbers -> full patterns (all variables)
# Ex: minterm_patterns([1, 4], 3) --> ["001", "100"]
def minterm_patterns(indices, n):
    patterns = []
    for index in indices:
        patterns.append(to_bits(index, n))
    return patterns
