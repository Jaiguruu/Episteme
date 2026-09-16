"""Cycle member A."""

from _edge.cyclic_b import CycleB


class CycleA:
    def ping(self):
        return CycleB()
