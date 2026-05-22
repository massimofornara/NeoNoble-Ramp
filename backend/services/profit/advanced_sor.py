class AdvancedSOR:

    async def route(self, venues):
        best = min(venues, key=lambda x: x["price"])
        return best
