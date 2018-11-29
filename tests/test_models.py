from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import SafeString
from graphviz import Digraph

from galahad.models import Process, Task
from galahad.tasks import StartView, HUMAN, MACHINE
from .testapp import models


class TestBaseProcess:
    def test_type_error(self):
        class TestProcess(Process):
            a = lambda s, t: None
            b = lambda s, t: None
            edges = [
                (a, b),
            ]  # lists are not hashable

            class Meta:
                abstract = True

    def test_node_name(self):
        class TestProcess(Process):
            a = lambda s, t: None
            b = lambda s, t: None
            c = lambda s, t: None
            edges = (
                (a, b),
            )

            class Meta:
                abstract = True

        assert TestProcess.a.node_name == 'a'
        assert TestProcess.b.node_name == 'b'
        with pytest.raises(AttributeError):
            TestProcess.c.node_name

    def test_node_type(self):
        class TestProcess(Process):
            a = StartView()
            b = lambda s, t: None
            c = lambda s, t: None
            edges = (
                (a, b),
            )

            class Meta:
                abstract = True

        assert TestProcess.a.node_type == HUMAN
        assert TestProcess.b.node_type == MACHINE
        with pytest.raises(AttributeError):
            TestProcess.c.node_type

    def test_node_type(self):
        class TestProcess(Process):
            a = StartView()
            b = lambda s, t: None
            c = lambda s, t: None
            edges = (
                (a, b),
            )

            class Meta:
                abstract = True

        assert TestProcess.a.process_cls == TestProcess
        assert TestProcess.b.process_cls == TestProcess
        with pytest.raises(AttributeError):
            TestProcess.c.process_cls


class TestProcess:

    def test_get_nodes(self):
        class TestProcess(Process):
            a = lambda s, t: None
            b = lambda s, t: None
            c = lambda s, t: None
            d = lambda s, t: None
            edges = (
                (a, b),
                (b, c),
                (a, c),
            )

            class Meta:
                abstract = True

        assert dict(TestProcess.get_nodes()) == {
            'a': TestProcess.a,
            'b': TestProcess.b,
            'c': TestProcess.c,
        }

    def test_get_node(self):
        class TestProcess(Process):
            a = lambda s, t: None
            b = lambda s, t: None
            c = lambda s, t: None
            edges = (
                (a, b),
            )

            class Meta:
                abstract = True

        assert TestProcess.get_node('a') == TestProcess.a
        with pytest.raises(KeyError):
            TestProcess.get_node('c')

    def test_get_next_nodes(self):
        class TestProcess(Process):
            a = lambda s, t: None
            b = lambda s, t: None
            c = lambda s, t: None
            edges = (
                (a, b),
                (b, c),
                (a, c),
            )

            class Meta:
                abstract = True

        assert list(TestProcess.get_next_nodes(TestProcess.a)) == [
            TestProcess.b,
            TestProcess.c,
        ]

        assert list(TestProcess.get_next_nodes(TestProcess.b)) == [
            TestProcess.c,
        ]

        assert list(TestProcess.get_next_nodes(TestProcess.c)) == []

    def test_get_absolute_url(self, db):
        process = models.SimpleProcess.start_method()
        assert process.get_absolute_url() == '/simple/1/'

    def test_get_override_url(self, db):
        process = models.SimpleProcess.start_method()
        assert process.get_override_url() == '/simple/1/override'

    def test_get_graph(self, fixturedir):
        graph = models.SimpleProcess.get_graph()
        assert isinstance(graph, Digraph)
        with open(str(fixturedir / 'simpleprocess.dot')) as fp:
            expected_graph = fp.read().splitlines()
        assert set(graph.body) == set(expected_graph[1:-1])

    def test_get_graph_svg(self, fixturedir):
        svg = models.SimpleProcess.get_graph_svg()
        assert isinstance(svg, SafeString)

    def test_get_instance_graph(self, db, fixturedir):
        process = models.SimpleProcess.start_method()
        graph = process.get_instance_graph()
        with open(str(fixturedir / 'simpleprocess_instance.dot')) as fp:
            expected_graph = fp.read().splitlines()
        assert set(graph.body) == set(expected_graph[1:-1])

    def test_get_instance_graph__manual_override(self, db, fixturedir, admin_client):
        process = models.SimpleProcess.start_method()
        url = reverse('simpleprocess:override', args=[process.pk])
        response = admin_client.post(url, data={'next_tasks': ['end']})
        assert response.status_code == 302
        assert process.task_set.get(node_name='manual_override')
        graph = process.get_instance_graph()
        with open(str(fixturedir / 'simpleprocess_instance_manual_override.dot')) as fp:
            expected_graph = fp.read().splitlines()
        assert set(graph.body) == set(expected_graph[1:-1])

    def test_get_instance_graph_svg(self, db, fixturedir):
        process = models.SimpleProcess.start_method()
        svg = process.get_instance_graph_svg()
        assert isinstance(svg, SafeString)

    def test_cancel(self, db):
        process = models.SimpleProcess.objects.create()
        process.task_set.create()
        assert process.task_set.scheduled().exists()
        process.cancel()
        assert not process.task_set.scheduled().exists()
        assert process.task_set.latest().completed_by_user is None
        assert process.task_set.latest().completed

    def test_cancel__with_user(self, db):
        process = models.SimpleProcess.objects.create()
        process.task_set.create()
        user = get_user_model().objects.create(
            email='spiderman@avengers.com',
            first_name='Peter',
            last_name='Parker',
            username='spidy',
        )
        process.cancel(user=user)
        assert process.task_set.latest().completed_by_user == user

    def test_cancel__with_anonymous_user(self, db):
        process = models.SimpleProcess.objects.create()
        process.task_set.create()
        user = AnonymousUser()
        process.cancel(user=user)
        assert process.task_set.latest().completed_by_user is None


class TestTaskQuerySet:

    def test_scheduled(self, db):
        process = models.SimpleProcess.objects.create()
        task = process.task_set.create()
        process.task_set.create(status=Task.CANCELED)
        assert process.task_set.scheduled().get() == task

    def test_succeeded(self, db):
        process = models.SimpleProcess.objects.create()
        task = process.task_set.create(status=Task.SUCCEEDED)
        process.task_set.create(status=Task.CANCELED)
        assert process.task_set.succeeded().get() == task

    def test_not_succeeded(self, db):
        process = models.SimpleProcess.objects.create()
        task = process.task_set.create()
        process.task_set.create(status=Task.SUCCEEDED)
        assert process.task_set.not_succeeded().get() == task

    def test_failed(self, db):
        process = models.SimpleProcess.objects.create()
        task = process.task_set.create(status=Task.FAILED)
        process.task_set.create(status=Task.CANCELED)
        assert process.task_set.failed().get() == task

    def test_canceled(self, db):
        process = models.SimpleProcess.objects.create()
        task = process.task_set.create(status=Task.CANCELED)
        process.task_set.create()
        assert process.task_set.canceled().get() == task

    def test_cancel__with_user(self, db):
        process = models.SimpleProcess.objects.create()
        process.task_set.create()
        user = get_user_model().objects.create(
            email='spiderman@avengers.com',
            first_name='Peter',
            last_name='Parker',
            username='spidy',
        )
        process.task_set.cancel(user=user)
        assert process.task_set.latest().completed_by_user == user

    def test_cancel__with_anonymous_user(self, db):
        process = models.SimpleProcess.objects.create()
        process.task_set.create()
        user = AnonymousUser()
        process.task_set.cancel(user=user)
        assert process.task_set.latest().completed_by_user is None


class TestTask:

    def test_start_next_tasks__default(self, db):
        process = models.SimpleProcess.objects.create()
        task = process.task_set.create(node_name='start_method')
        task.finish()
        tasks = task.start_next_tasks()
        assert len(tasks) == 1
        assert tasks[0].node_name == 'save_the_princess'
        assert process.task_set.scheduled().get() == tasks[0]

    def test_start_next_tasks__specific_next_task(self, db):
        process = models.SimpleProcess.objects.create()
        task = process.task_set.create(node_name='start_method')
        task.finish()
        tasks = task.start_next_tasks(next_nodes=[models.SimpleProcess.end])
        assert len(tasks) == 1
        assert tasks[0].node_name == 'end'
        assert process.task_set.latest() == tasks[0]

    @patch('galahad.celery.task_wrapper.retry')
    def test_start_next_tasks__multiple_next_tasks(self, retry, db):
        process = models.SplitJoinProcess.objects.create()
        task = process.task_set.create(node_name='split')
        tasks = task.start_next_tasks(next_nodes=[
            models.SplitJoinProcess.batman, models.SplitJoinProcess.robin
        ])
        assert len(tasks) == 2

    @patch('galahad.celery.task_wrapper.retry')
    def test_start_next_tasks__custom_task_creation(self, retry, db):
        process = models.SplitJoinProcess.objects.create()
        task = process.task_set.create(node_name='batman')
        tasks = task.start_next_tasks(next_nodes=[
            models.SplitJoinProcess.join
        ])
        join1 = tasks[0]

        task = process.task_set.create(node_name='robin')
        tasks = task.start_next_tasks(next_nodes=[
            models.SplitJoinProcess.join
        ])
        assert tasks[0] == join1

    def test_fail(self, db):
        process = models.SimpleProcess.objects.create()
        task = process.task_set.create()
        try:
            raise IOError("nope")
        except IOError:
            task.fail()

        assert task.status == task.FAILED
        assert task.exception == "OSError: nope"
        assert 'Traceback (most recent call last):\n' in task.stacktrace
        assert '    raise IOError("nope")\n' in task.stacktrace
        assert 'OSError: nope\n' in task.stacktrace

    def test_cancel(self, db):
        process = models.SimpleProcess.objects.create()
        task = process.task_set.create()
        task.cancel()
        assert task.status == task.CANCELED
        assert task.completed_by_user is None
        assert task.completed

    def test_cancel__with_user(self, db):
        process = models.SimpleProcess.objects.create()
        task = process.task_set.create()
        user = get_user_model().objects.create(
            email='spiderman@avengers.com',
            first_name='Peter',
            last_name='Parker',
            username='spidy',
        )
        task.cancel(user=user)
        assert task.completed_by_user == user

    def test_cancel__with_anonymous_user(self, db):
        process = models.SimpleProcess.objects.create()
        task = process.task_set.create()
        user = AnonymousUser()
        task.cancel(user=user)
        assert task.completed_by_user is None

    def test_save__modified_date(self, db):
        process = models.SimpleProcess.objects.create()
        task = process.task_set.create()
        modified_date = task.modified
        task.save(update_fields=[])
        task.refresh_from_db()
        assert task.modified > modified_date

    def test_save__no_update_fields(self, db):
        process = models.SimpleProcess.objects.create()
        task = process.task_set.create()
        with pytest.raises(ValueError) as e:
            task.save()
        assert "You need to provide explicit 'update_fields' to avoid race conditions." in str(e)
