import transaction
import time
from zc.async.testing import wait_for_result
from Products.PloneTestCase.PloneTestCase import default_user
from plone.app.async.tests.base import AsyncTestCase


def addNumbers(x1, x2):
    return x1 + x2


def doom():
    doom.retries += 1
    transaction.doom()


def fail_once():
    fail_once.retries += 1
    if fail_once.retries == 1:
        fail_once.start = time.time()
        raise Exception('Job failed.')
    return time.time() - fail_once.start


class TestJob(AsyncTestCase):

    def test_add_job(self):
        """Tests adding a computational job and getting the result.
        """
        from plone.app.async import Job, queue
        job = queue(Job(addNumbers, 40, 2))
        transaction.commit()
        self.assertEqual(job.status, u'pending-status')
        wait_for_result(job)
        self.assertEqual(job.status, u'completed-status')
        self.assertEqual(job.result, 42)

    def test_add_persistent(self):
        """Adding a job that creates persistent objects.
        """
        from plone.app.async import Job, queue
        self.setRoles(['Manager'])
        job = queue(Job(self.folder.invokeFactory, 'Document', 'anid',
            title='atitle', description='adescr', text='abody'))
        transaction.commit()
        self.assertEqual(job.status, u'pending-status')
        wait_for_result(job)
        self.assertEqual(job.status, u'completed-status')
        self.assertEqual(job.result, 'anid')
        self.failUnless('anid' in self.folder.objectIds())
        document = self.folder['anid']
        self.assertEqual(document.Creator(), default_user)

    def test_retry(self):
        """A job that causes a conflict while committing should be retried."""
        doom.retries = 0
        from plone.app.async import Job, queue
        job = queue(Job(doom))
        transaction.commit()
        wait_for_result(job)
        self.assertTrue(job.result.type is transaction.interfaces.DoomedTransaction)
        self.assertEqual(5, doom.retries)

    def test_delayed_retry(self):
        from datetime import timedelta
        from plone.app.async import Job, queue, RetryWithDelay
        fail_once.retries = 0
        job = queue(Job(fail_once))
        job.retry_policy_factory = RetryWithDelay(timedelta(seconds=5))
        transaction.commit()
        wait_for_result(job)
        self.assertTrue(2, fail_once.retries)
        self.assertTrue(job.result > 5)