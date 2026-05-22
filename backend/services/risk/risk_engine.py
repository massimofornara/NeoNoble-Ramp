class RiskEngine:

    def __init__(self):
        self.max_exposure = 100000

    def check(self, exposure):
        if exposure > self.max_exposure:
            return False
        return True
