"""
Test CRUD & luồng nghiệp vụ Ticket — tập trung vào phân quyền giữa nhân viên
(agent) và quản lý (manager/admin), theo đúng quy tắc trong
`ticket_service.user_can_access_ticket()`:
    - admin, manager: luôn được phép thao tác trên MỌI ticket.
    - agent: CHỈ được phép trên ticket đang được gán (assigned_to_agent_id == mình).
"""

from app.models.user import UserRole


class TestStatusUpdatePermission:
    """PATCH /tickets/{id}/status — endpoint duy nhất cho phép cả agent lẫn manager/admin."""

    def test_agent_can_update_status_of_own_assigned_ticket(self, client, make_user, make_ticket, auth_headers):
        agent = make_user(UserRole.AGENT)
        ticket = make_ticket(assigned_to_agent_id=agent.id)

        resp = client.patch(
            f"/api/v1/tickets/{ticket.id}/status",
            json={"status": "processing"},
            headers=auth_headers(agent),
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "processing"

    def test_agent_cannot_update_status_of_ticket_assigned_to_another_agent(
        self, client, make_user, make_ticket, auth_headers
    ):
        agent_a = make_user(UserRole.AGENT)
        agent_b = make_user(UserRole.AGENT)
        ticket = make_ticket(assigned_to_agent_id=agent_b.id)

        resp = client.patch(
            f"/api/v1/tickets/{ticket.id}/status",
            json={"status": "processing"},
            headers=auth_headers(agent_a),
        )

        assert resp.status_code == 403

    def test_agent_cannot_update_status_of_unassigned_ticket(
        self, client, make_user, make_ticket, auth_headers
    ):
        agent = make_user(UserRole.AGENT)
        ticket = make_ticket(assigned_to_agent_id=None)

        resp = client.patch(
            f"/api/v1/tickets/{ticket.id}/status",
            json={"status": "processing"},
            headers=auth_headers(agent),
        )

        assert resp.status_code == 403

    def test_manager_can_update_status_of_any_ticket(self, client, make_user, make_ticket, auth_headers):
        agent = make_user(UserRole.AGENT)
        manager = make_user(UserRole.MANAGER)
        ticket = make_ticket(assigned_to_agent_id=agent.id)

        resp = client.patch(
            f"/api/v1/tickets/{ticket.id}/status",
            json={"status": "closed"},
            headers=auth_headers(manager),
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "closed"
        # Đóng ticket phải ghi nhận closed_at (dùng để tính thời gian xử lý).
        assert resp.json()["closed_at"] is not None

    def test_admin_can_update_status_of_any_ticket(self, client, make_user, make_ticket, auth_headers):
        agent = make_user(UserRole.AGENT)
        admin = make_user(UserRole.ADMIN)
        ticket = make_ticket(assigned_to_agent_id=agent.id)

        resp = client.patch(
            f"/api/v1/tickets/{ticket.id}/status",
            json={"status": "waiting"},
            headers=auth_headers(admin),
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "waiting"


class TestAssignPermission:
    """PATCH /tickets/{id}/assign, /unassign — chỉ admin/manager (theo require_roles)."""

    def test_agent_cannot_assign_ticket(self, client, make_user, make_ticket, auth_headers):
        agent = make_user(UserRole.AGENT)
        other_agent = make_user(UserRole.AGENT)
        ticket = make_ticket()

        resp = client.patch(
            f"/api/v1/tickets/{ticket.id}/assign",
            json={"agent_id": other_agent.id},
            headers=auth_headers(agent),
        )

        assert resp.status_code == 403

    def test_manager_can_assign_ticket_to_agent(self, client, make_user, make_ticket, auth_headers):
        manager = make_user(UserRole.MANAGER)
        agent = make_user(UserRole.AGENT)
        ticket = make_ticket()

        resp = client.patch(
            f"/api/v1/tickets/{ticket.id}/assign",
            json={"agent_id": agent.id},
            headers=auth_headers(manager),
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["assigned_to_agent_id"] == agent.id
        # Ticket "new" phải tự chuyển sang "processing" khi được phân công.
        assert resp.json()["status"] == "processing"

    def test_agent_cannot_unassign_ticket(self, client, make_user, make_ticket, auth_headers):
        agent = make_user(UserRole.AGENT)
        ticket = make_ticket(assigned_to_agent_id=agent.id)

        resp = client.patch(
            f"/api/v1/tickets/{ticket.id}/unassign",
            headers=auth_headers(agent),
        )

        assert resp.status_code == 403


class TestDeletePermission:
    """DELETE /tickets/{id} — chỉ admin (theo require_roles("admin"))."""

    def test_manager_cannot_delete_ticket(self, client, make_user, make_ticket, auth_headers):
        manager = make_user(UserRole.MANAGER)
        ticket = make_ticket()

        resp = client.delete(f"/api/v1/tickets/{ticket.id}", headers=auth_headers(manager))

        assert resp.status_code == 403

    def test_admin_can_delete_ticket(self, client, make_user, make_ticket, auth_headers):
        admin = make_user(UserRole.ADMIN)
        ticket = make_ticket()

        resp = client.delete(f"/api/v1/tickets/{ticket.id}", headers=auth_headers(admin))

        assert resp.status_code == 204


class TestInteractionPermission:
    """POST/DELETE /tickets/{id}/interactions — cùng quy tắc user_can_access_ticket()."""

    def test_unrelated_agent_cannot_add_interaction(self, client, make_user, make_ticket, auth_headers):
        agent_a = make_user(UserRole.AGENT)
        agent_b = make_user(UserRole.AGENT)
        ticket = make_ticket(assigned_to_agent_id=agent_b.id)

        resp = client.post(
            f"/api/v1/tickets/{ticket.id}/interactions",
            json={"sender_type": "agent", "content": "Ghi chu noi bo"},
            headers=auth_headers(agent_a),
        )

        assert resp.status_code == 403

    def test_assigned_agent_can_add_interaction(self, client, make_user, make_ticket, auth_headers):
        agent = make_user(UserRole.AGENT)
        ticket = make_ticket(assigned_to_agent_id=agent.id)

        resp = client.post(
            f"/api/v1/tickets/{ticket.id}/interactions",
            json={"sender_type": "agent", "content": "Da lien he khach hang"},
            headers=auth_headers(agent),
        )

        assert resp.status_code == 201, resp.text

    def test_agent_cannot_delete_interaction(self, client, make_user, make_ticket, auth_headers, db_session):
        from app.models.interaction_history import InteractionHistory, SenderType

        agent = make_user(UserRole.AGENT)
        ticket = make_ticket(assigned_to_agent_id=agent.id)
        interaction = InteractionHistory(
            ticket_id=ticket.id, sender_type=SenderType.AGENT, content="Noi dung"
        )
        db_session.add(interaction)
        db_session.commit()
        db_session.refresh(interaction)

        resp = client.delete(
            f"/api/v1/tickets/{ticket.id}/interactions/{interaction.id}",
            headers=auth_headers(agent),
        )

        # delete_interaction giới hạn admin/manager (chặt hơn cả sửa) -> agent bị từ chối.
        assert resp.status_code == 403


class TestListAndCreatePermission:
    """List/create ticket: mọi nhân viên đã đăng nhập đều được phép."""

    def test_agent_can_list_tickets(self, client, make_user, make_ticket, auth_headers):
        agent = make_user(UserRole.AGENT)
        make_ticket()

        resp = client.get("/api/v1/tickets", headers=auth_headers(agent))

        assert resp.status_code == 200

    def test_unauthenticated_request_is_rejected(self, client, make_ticket):
        make_ticket()

        resp = client.get("/api/v1/tickets")

        assert resp.status_code == 401
