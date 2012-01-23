from datetime import datetime
from zope.component import getUtility
from Products.Five import BrowserView
from zc.async.interfaces import ACTIVE, COMPLETED
from zc.async.utils import custom_repr
from zc.twist import Failure
from plone.app.async.interfaces import IAsyncService
from webdav.xmltools import escape
from ZODB.utils import p64, u64
import pytz


def filter_jobs(jobs, portal_path):
    for job in jobs:
        if getattr(job, 'portal_path', None) == portal_path:
            yield job

def get_failure(job):
    if job.status == COMPLETED and isinstance(job.result, Failure):
        return job.result
    elif job._retry_policy and job._retry_policy.data.get('job_error', 0):
        return job._retry_policy.data['last_job_error']


class QueueView(BrowserView):

    def __call__(self):
        portal_path = self.context.getPhysicalPath()
        self.now = datetime.now(pytz.UTC)
        self.queued_jobs = []
        self.active_jobs = []
        self.completed_jobs = []
        self.dead_jobs = []

        service = getUtility(IAsyncService)
        queue = service.getQueues()['']
        for job in filter_jobs(queue, portal_path):
            self.queued_jobs.append(job)
        for da in queue.dispatchers.values():
            for agent in da.values():
                for job in filter_jobs(agent, portal_path):
                    self.active_jobs.append(job)
                for job in filter_jobs(agent.completed, portal_path):
                    if isinstance(job.result, Failure):
                        self.dead_jobs.append(job)
                    else:
                        self.completed_jobs.append(job)

        return self.index()

    def format_timing(self, job):
        if job.status == COMPLETED:
            return 'Completed at %s' % job.active_end
        elif job.status == ACTIVE:
            return 'Started at %s' % job.active_start
        else:
            if job.begin_after > self.now:
                retries = 0
                if job._retry_policy:
                    retries = job._retry_policy.data.get('job_error', 0)
                if retries:
                    return 'Retry #%s scheduled for %s' % (retries, job.begin_after)
                else:
                    return 'Scheduled for %s' % job.begin_after
            else:
                return 'Queued at %s' % job.begin_after
    
    def format_args(self, job):
        args = ', '.join(custom_repr(a) for a in job.args)
        kwargs = ', '.join(k + "=" + custom_repr(v) for k, v in job.kwargs.items())
        if args and kwargs:
            args += ", " + kwargs
        elif kwargs:
            args = kwargs
        return args
    
    def format_failure(self, job):
        failure = get_failure(job)
        if failure is None:
            return ''
        
        res = '%s: %s' % (failure.type.__name__, failure.getErrorMessage())
        res += ' <a href="%s/manage-job-error?id=%s">Details</a>' % (self.context.absolute_url(), u64(job._p_oid))
        return res

    def custom_repr(self, ob):
        return custom_repr(ob)


class TracebackView(BrowserView):

    def __call__(self, id):
        queue = getUtility(IAsyncService).getQueues()['']
        job = queue._p_jar.get(p64(int(id)))
        failure = get_failure(job)
        return escape(failure.getTraceback())


# Need to show:
# - ideally, progress bar based on job annotations
# - format times in local timezone

import time
from plone.app.async import Job, queue, RetryWithDelay

def foobar():
    time.sleep(5)
    raise Exception('Oh no!')


class TestJob(BrowserView):

    def __call__(self):
        job = queue(Job(foobar))
        job.retry_policy_factory = RetryWithDelay()
        return self.request.response.redirect('http://localhost:8080/Plone/manage-job-queue')