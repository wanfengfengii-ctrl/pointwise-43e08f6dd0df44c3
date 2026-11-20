from fractions import Fraction
from math import comb


def exact_upper_tail(total: int, successes: int, null_rate: Fraction | int) -> Fraction:
    if type(total) is not int or type(successes) is not int or not 0 <= successes <= total or total == 0:
        raise ValueError('expected a positive trial count and a valid success count')
    if type(null_rate) not in (Fraction, int) or not 0 <= null_rate <= 1:
        raise ValueError('null rate must be an exact rational in [0, 1]')
    if successes == 0 or null_rate == 1:
        return Fraction(1)
    if null_rate == 0:
        return Fraction(0)

    a, b = null_rate.numerator, null_rate.denominator
    failures = b - a
    numerator = sum(
        comb(total, count) * a**count * failures**(total - count)
        for count in range(successes, total + 1)
    )
    return Fraction(numerator, b**total)


def is_significant(p_value: Fraction, alpha_bps: int) -> bool:
    if type(p_value) is not Fraction or not 0 <= p_value <= 1:
        raise ValueError('p value must be an exact fraction in [0, 1]')
    if type(alpha_bps) is not int or not 1 <= alpha_bps <= 10_000:
        raise ValueError('alpha must be an integer from 1 to 10000')
    return p_value <= Fraction(alpha_bps, 10_000)
