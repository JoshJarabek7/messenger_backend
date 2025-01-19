import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core.meta import SingletonMeta


class TestSingleton(metaclass=SingletonMeta):
    """Test class using SingletonMeta."""

    def __init__(self, value: int = 0):
        self.value = value


def test_singleton_basic():
    """Test basic singleton behavior."""
    # First instance
    instance1 = TestSingleton(1)
    assert instance1.value == 1

    # Second instance should be the same object
    instance2 = TestSingleton(2)
    assert instance2.value == 1  # Value should not change
    assert instance1 is instance2  # Should be same object


def test_singleton_thread_safety():
    """Test singleton thread safety."""

    def create_instance(value: int) -> TestSingleton:
        return TestSingleton(value)

    # Create instances from multiple threads
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(create_instance, i) for i in range(10)]
        instances = [f.result() for f in futures]

    # All instances should be the same object
    first = instances[0]
    assert all(instance is first for instance in instances)
    assert all(instance.value == first.value for instance in instances)


def test_singleton_multiple_classes():
    """Test that different classes get different singletons."""

    class AnotherSingleton(metaclass=SingletonMeta):
        def __init__(self, value: int = 0):
            self.value = value

    # Create instances of both classes
    test_instance = TestSingleton(1)
    another_instance = AnotherSingleton(2)

    # Should be different objects
    assert test_instance is not another_instance
    assert test_instance.value == 1
    assert another_instance.value == 2

    # But same class instances should be same object
    assert TestSingleton(3) is test_instance
    assert AnotherSingleton(4) is another_instance
