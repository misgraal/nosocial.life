from dataclasses import dataclass

@dataclass
class CheckResult:
    result: bool

def check(number: int, correct_number: int) -> CheckResult:
    if number == correct_number:
        return CheckResult(True)
    else:
        return CheckResult(False)