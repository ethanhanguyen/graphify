"""Python call resolution fixture — defines a class with method calls for testing."""
import math


def helper_func(x: int) -> int:
    return x * 2


class Calculator:
    def __init__(self, initial: int = 0):
        self.value = initial

    def add(self, amount: int) -> int:
        return self.value + amount

    def compute(self, x: int) -> int:
        result = helper_func(x)
        doubled = self.add(result)
        final = math.floor(doubled)
        return final


class AdvancedCalc(Calculator):
    def multiply(self, factor: int) -> int:
        return self.value * factor

    def compute(self, x: int) -> int:
        interim = helper_func(x)
        doubled = self.add(interim)
        final = math.ceil(doubled)
        return final
