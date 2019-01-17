import collections
import statistics
import time
from typing import Iterable, List

from celery.result import AsyncResult, result_from_tuple
from celery.signals import task_postrun, task_prerun
from django.core.cache import caches
from django.utils.translation import ugettext_lazy as _
from rest_framework import exceptions, status

from common.exceptions import TryLater

d = {}

average_time = collections.deque(maxlen=5)
average_time.append(2)


@task_prerun.connect
def task_prerun_handler(signal, sender, task_id, task, **kwargs):
    d[task_id] = time.time()


@task_postrun.connect
def task_postrun_handler(signal, sender, task_id, task, **kwargs):
    try:
        cost = time.time() - d.pop(task_id)
        average_time.append(cost)
    except KeyError:
        cost = -1


def get_min_state(tasks: Iterable[AsyncResult]) -> str:
    return min(tasks, key=lambda task: [
        "FAILURE",
        "RETRY",
        "PENDING",
        "STARTED",
        "SUCCESS",
    ].index(task.state)).state


class CachedDelay(object):
    tasks_cache = caches['deferred-tasks']

    def __init__(self, cache_name: str) -> None:
        super().__init__()
        self.cache_name = cache_name
        self.cache = caches[cache_name]

    def get_many(self, keys: List[str], generator, detail=None) -> dict:
        results = self.cache.get_many(keys)
        if set(results.keys()) == set(keys):
            return results

        task_keys = {self.cache_name + '|' + key: key for key in keys}
        task_ids_dict = self.tasks_cache.get_many(task_keys.keys())
        not_cached_task_keys = set(task_keys.keys()) - set(task_ids_dict.keys())
        keys_to_tasks = {}
        if not_cached_task_keys:
            for task_key in not_cached_task_keys:
                task = generator(task_keys[task_key])
                task_id_tuple = task.as_tuple()
                self.tasks_cache.set(task_key, task_id_tuple)
                keys_to_tasks[task_key] = task

        keys_to_tasks.update(
            {task_key: result_from_tuple(task_id_tuple) for task_key, task_id_tuple in task_ids_dict.items()}
        )

        for task_key, task in keys_to_tasks.items():
            if task.state == 'FAILURE':
                self.tasks_cache.delete(task_key)

        min_state = get_min_state(keys_to_tasks.values())
        if min_state == 'FAILURE':
            raise self.failure()
        if min_state in ['PENDING', 'STARTED', 'RETRY']:
            raise self.try_later(keys_to_tasks.values(), detail)

        results = {task_keys[task_key]: task.result for task_key, task in keys_to_tasks.items()}
        self.cache.set_many(results)
        return results

    def get(self, key: str, generator, detail=None):
        return self.get_many([key], lambda _: generator(), detail).get(key)

    def __call__(self, key: str, generator, detail=None):
        return self.get(key, generator, detail)

    def try_later(self, tasks: Iterable[AsyncResult], detail: str = None):
        wait = statistics.mean(average_time)
        min_state = get_min_state(tasks)

        raise TryLater(
            detail={
                "detail": detail if detail else _("Request was accepted."),
                "status": min_state,
                "completion": {
                    "estimate": time.time() + wait,
                    # "rejected-after": "Fri Sep 09 2011 12:00:00 GMT-0400",
                    "retry-after": wait,
                },
                # "tracking": {
                #     "url": "http://server/status?id=" + task.id
                # }
            },
            code=status.HTTP_202_ACCEPTED,
            wait=wait,
        )

    def failure(self):
        raise exceptions.NotFound()


def exception_handler(exc, context):
    from rest_framework.views import exception_handler as default_handler

    response = default_handler(exc, context)
    if isinstance(exc, exceptions.APIException):
        codes = exc.get_codes()
        if not isinstance(exc.detail, (list, dict)):
            response.data['code'] = codes

    return response
