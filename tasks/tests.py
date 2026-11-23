import datetime
from unittest.mock import patch
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from tasks.models import Task
from tasks.idempotency import IDEMPOTENCY_STORE


class TaskAPITestCase(APITestCase):

    def setUp(self):
        IDEMPOTENCY_STORE.clear()
        self.today = datetime.date.today()
        self.tomorrow = self.today + datetime.timedelta(days=1)

    # ---------------------------------------------------------
    # Step 2 & 3: CRUD & Validation & Consistent Error Shape
    # ---------------------------------------------------------
    def test_create_task_success(self):
        url = reverse('task-list')
        payload = {
            "title": "Buy groceries",
            "description": "Milk, eggs, and bread",
            "completed": False,
            "due_date": self.tomorrow.isoformat(),
            "priority": "high"
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], "Buy groceries")
        self.assertEqual(response.data['priority'], "high")
        self.assertEqual(Task.objects.count(), 1)

    def test_create_task_validation_empty_title_and_description(self):
        url = reverse('task-list')
        payload = {
            "title": "   ",
            "description": "",
            "completed": False,
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(response.data["error"]["message"], "Validation failed")
        details = response.data["error"]["details"]
        fields = [d["field"] for d in details]
        self.assertIn("title", fields)
        self.assertIn("description", fields)

    def test_create_task_validation_invalid_boolean(self):
        url = reverse('task-list')
        payload = {
            "title": "Valid title",
            "description": "Valid description",
            "completed": "not-a-boolean",
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        fields = [d["field"] for d in response.data["error"]["details"]]
        self.assertIn("completed", fields)

    def test_create_task_validation_impossible_date(self):
        url = reverse('task-list')
        payload = {
            "title": "Leap year task",
            "description": "Testing invalid date",
            "due_date": "2026-02-30"  # Invalid date
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        fields = [d["field"] for d in response.data["error"]["details"]]
        self.assertIn("due_date", fields)

    def test_create_task_validation_invalid_priority(self):
        url = reverse('task-list')
        payload = {
            "title": "Priority test",
            "description": "Invalid priority choice",
            "priority": "super-urgent"
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        fields = [d["field"] for d in response.data["error"]["details"]]
        self.assertIn("priority", fields)

    def test_retrieve_not_found_returns_consistent_error(self):
        url = reverse('task-detail', kwargs={'pk': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "NOT_FOUND")
        self.assertEqual(response.data["error"]["message"], "Task not found")
        self.assertEqual(response.data["error"]["details"], [])

    def test_update_and_destroy_task(self):
        task = Task.objects.create(title="Old title", description="Old desc")
        url = reverse('task-detail', kwargs={'pk': task.id})

        # Partial update
        patch_res = self.client.patch(url, {"title": "New title"}, format='json')
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data["title"], "New title")

        # Delete
        delete_res = self.client.delete(url)
        self.assertEqual(delete_res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Task.objects.count(), 0)

        # Delete unknown id -> 404
        delete_again = self.client.delete(url)
        self.assertEqual(delete_again.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(delete_again.data["error"]["code"], "NOT_FOUND")

    # ---------------------------------------------------------
    # Step 4: Natural-Language Task Creation (/from-text/)
    # ---------------------------------------------------------
    def test_from_text_rule_based_success(self):
        url = reverse('task-from-text')
        payload = {"text": "Remind me to pay rent on the 1st of every month"}
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "Pay rent")
        self.assertIn("month", response.data["recurrence"])
        self.assertIsNotNone(response.data["due_date"])
        self.assertEqual(Task.objects.count(), 1)

    def test_from_text_tomorrow_phrase(self):
        url = reverse('task-from-text')
        payload = {"text": "Submit quarterly report tomorrow urgent"}
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["due_date"], self.tomorrow.isoformat())
        self.assertEqual(response.data["priority"], "high")

    def test_from_text_empty_input_returns_400(self):
        url = reverse('task-from-text')
        response = self.client.post(url, {"text": "   "}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_from_text_parser_failure_returns_502_and_saves_nothing(self):
        """Simulate bad model / parser output with empty title, ensuring 502 and zero rows saved."""
        url = reverse('task-from-text')
        with patch('tasks.views.parse_task_text', return_value={"title": "", "description": ""}):
            response = self.client.post(url, {"text": "Do something"}, format='json')
            self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
            self.assertEqual(response.data["error"]["code"], "PARSER_VALIDATION_ERROR")
            self.assertEqual(Task.objects.count(), 0)

    def test_from_text_parser_exception_returns_502(self):
        url = reverse('task-from-text')
        with patch('tasks.views.parse_task_text', side_effect=RuntimeError("Parsing crash")):
            response = self.client.post(url, {"text": "Crash me"}, format='json')
            self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
            self.assertEqual(response.data["error"]["code"], "PARSER_ERROR")
            self.assertEqual(Task.objects.count(), 0)

    def test_from_text_llm_mode_without_key_returns_503(self):
        url = reverse('task-from-text')
        with patch('django.conf.settings.LLM_API_KEY', None):
            response = self.client.post(url, {"text": "Do something", "use_llm": True}, format='json')
            self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            self.assertEqual(response.data["error"]["code"], "SERVICE_UNAVAILABLE")

    # ---------------------------------------------------------
    # Step 5: Subtasks and Breakdown
    # ---------------------------------------------------------
    def test_create_and_list_subtasks(self):
        parent = Task.objects.create(title="Parent Project", description="Main project task")
        url = reverse('task-subtasks', kwargs={'pk': parent.id})

        # Create subtask
        subtask_payload = {
            "title": "Subtask 1",
            "description": "Step 1 details",
            "priority": "low"
        }
        create_res = self.client.post(url, subtask_payload, format='json')
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_res.data["parent"], parent.id)

        # List subtasks
        list_res = self.client.get(url)
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res.data), 1)
        self.assertEqual(list_res.data[0]["title"], "Subtask 1")

    def test_subtask_cannot_have_subtasks(self):
        parent = Task.objects.create(title="Parent", description="Top level")
        subtask = Task.objects.create(title="Child", description="Level 1 child", parent=parent)

        url = reverse('task-subtasks', kwargs={'pk': subtask.id})
        response = self.client.post(url, {"title": "Grandchild", "description": "Invalid"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_SUBTASK")

    def test_parent_deletion_cascades_to_subtasks(self):
        parent = Task.objects.create(title="Parent", description="Will be deleted")
        Task.objects.create(title="Child 1", description="C1", parent=parent)
        Task.objects.create(title="Child 2", description="C2", parent=parent)
        self.assertEqual(Task.objects.count(), 3)

        parent.delete()
        self.assertEqual(Task.objects.count(), 0)

    def test_breakdown_task_success(self):
        parent = Task.objects.create(
            title="Prepare launch presentation",
            description="Draft slides and rehearse speech and prepare handouts"
        )
        url = reverse('task-breakdown', kwargs={'pk': parent.id})
        response = self.client.post(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertGreaterEqual(len(response.data), 2)
        self.assertEqual(parent.subtasks.count(), len(response.data))

    def test_breakdown_on_subtask_rejected(self):
        parent = Task.objects.create(title="Parent", description="P")
        subtask = Task.objects.create(title="Child", description="C", parent=parent)
        url = reverse('task-breakdown', kwargs={'pk': subtask.id})
        response = self.client.post(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_BREAKDOWN")

    def test_breakdown_validation_failure_saves_nothing(self):
        parent = Task.objects.create(title="Parent", description="P")
        url = reverse('task-breakdown', kwargs={'pk': parent.id})
        with patch('tasks.views.break_down_task', return_value=[{"title": "", "description": ""}]):
            response = self.client.post(url, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(parent.subtasks.count(), 0)

    # ---------------------------------------------------------
    # Step 6: Idempotent Creation
    # ---------------------------------------------------------
    def test_idempotency_key_same_body_returns_cached_response(self):
        url = reverse('task-list')
        payload = {"title": "Idempotent task", "description": "Safe retry"}
        headers = {"HTTP_IDEMPOTENCY_KEY": "key-abc-123"}

        # First request
        res1 = self.client.post(url, payload, format='json', **headers)
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        created_id = res1.data["id"]

        # Duplicate request with same key & body
        res2 = self.client.post(url, payload, format='json', **headers)
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res2.data["id"], created_id)

        # Database must only have 1 row
        self.assertEqual(Task.objects.count(), 1)

    def test_idempotency_key_different_body_returns_422(self):
        url = reverse('task-list')
        headers = {"HTTP_IDEMPOTENCY_KEY": "key-fixed-456"}

        res1 = self.client.post(url, {"title": "Version 1", "description": "D1"}, format='json', **headers)
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        res2 = self.client.post(url, {"title": "Version 2 Different", "description": "D2"}, format='json', **headers)
        self.assertEqual(res2.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(res2.data["error"]["code"], "IDEMPOTENCY_CONFLICT")
        self.assertEqual(Task.objects.count(), 1)

    def test_idempotency_failed_request_does_not_cache(self):
        url = reverse('task-list')
        headers = {"HTTP_IDEMPOTENCY_KEY": "retry-key-789"}

        # 1. Send invalid payload
        res1 = self.client.post(url, {"title": ""}, format='json', **headers)
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)

        # 2. Fix payload and retry with same key -> should succeed
        res2 = self.client.post(url, {"title": "Fixed title", "description": "Fixed desc"}, format='json', **headers)
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Task.objects.count(), 1)

    # ---------------------------------------------------------
    # Step 7: Filtering, Search, Ordering, and Pagination
    # ---------------------------------------------------------
    def test_filtering_search_ordering_pagination_together(self):
        url = reverse('task-list')

        # Create tasks
        Task.objects.create(title="Alpha Design", description="Frontend mockup", priority="high", completed=False, due_date="2026-12-01")
        Task.objects.create(title="Beta API Design", description="Backend endpoints", priority="high", completed=False, due_date="2026-11-25")
        Task.objects.create(title="Gamma Testing", description="Unit tests", priority="low", completed=False, due_date="2026-11-20")
        Task.objects.create(title="Delta Design", description="Already done", priority="high", completed=True, due_date="2026-10-15")

        # Query combining filtering, search, ordering, pagination
        params = {
            "completed": "false",
            "priority": "high",
            "search": "Design",
            "ordering": "due_date",
            "page": 1,
            "page_size": 2
        }
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertEqual(response.data["count"], 2)  # Alpha & Beta match
        # Sorted by due_date ascending: Beta (2026-11-25) should be first, then Alpha (2026-12-01)
        self.assertEqual(response.data["results"][0]["title"], "Beta API Design")
        self.assertEqual(response.data["results"][1]["title"], "Alpha Design")
