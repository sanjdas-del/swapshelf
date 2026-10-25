from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from market.forms import ProfileForm
from market.models import Listing, Message, Thread


class BoardTests(TestCase):
    def test_public_board_hides_seller_note(self):
        listing = Listing.objects.get(title="67W USB-C charger")
        home = self.client.get(reverse("home"))
        self.assertContains(home, "67W USB-C charger")
        self.assertNotContains(home, "SWAP-7741")

        detail = self.client.get(reverse("listing_detail", args=[listing.pk]))
        self.assertContains(detail, "Apple brick")
        self.assertNotContains(detail, "SWAP-7741")
        self.assertNotContains(detail, "Edit listing")

        bikes = self.client.get(reverse("home"), {"category": "bikes"})
        self.assertContains(bikes, "Campus bike, blue frame")
        self.assertNotContains(bikes, "67W USB-C charger")

    def test_owner_can_post_edit_and_mark_sold(self):
        self.assertTrue(self.client.login(username="alex", password="campus123"))
        created = self.client.post(
            reverse("listing_new"),
            {
                "title": "Calc textbook",
                "description": "No highlighting.",
                "price": "12.00",
                "category": "books",
                "seller_note": "Meet at the library desk.",
            },
        )
        listing = Listing.objects.get(title="Calc textbook")
        self.assertRedirects(created, reverse("listing_detail", args=[listing.pk]))
        self.assertEqual(listing.owner.username, "alex")
        self.assertEqual(listing.seller_note, "Meet at the library desk.")

        detail = self.client.get(reverse("listing_detail", args=[listing.pk]))
        self.assertContains(detail, "Calc textbook")
        self.assertContains(detail, "Edit listing")
        self.assertNotContains(detail, "library desk")
        self.assertContains(self.client.get(reverse("home")), "Calc textbook")

        edited = self.client.post(
            reverse("listing_edit", args=[listing.pk]),
            {
                "title": "Calc textbook",
                "description": "No highlighting. Paperback.",
                "price": "9.00",
                "category": "books",
                "seller_note": "Meet at the library desk.",
            },
        )
        self.assertRedirects(edited, reverse("listing_detail", args=[listing.pk]))
        listing.refresh_from_db()
        self.assertEqual(listing.price, 9)
        self.assertContains(self.client.get(reverse("listing_edit", args=[listing.pk])), "library desk")

        charger = Listing.objects.get(title="67W USB-C charger")
        self.assertContains(self.client.get(reverse("listing_edit", args=[charger.pk])), "SWAP-7741")

        sold = self.client.post(reverse("listing_sold", args=[listing.pk]))
        self.assertRedirects(sold, reverse("listing_detail", args=[listing.pk]))
        listing.refresh_from_db()
        self.assertEqual(listing.status, "sold")
        self.assertContains(self.client.get(reverse("listing_detail", args=[listing.pk])), "sold")

    def test_other_user_cannot_edit_sold_delete_or_read_thread(self):
        listing = Listing.objects.get(title="67W USB-C charger")
        thread = Thread.objects.get(listing__title="Campus bike, blue frame")
        self.assertTrue(self.client.login(username="sam", password="foundit!"))

        edit = self.client.get(reverse("listing_edit", args=[listing.pk]))
        self.assertEqual(edit.status_code, 404)
        self.assertNotContains(edit, "SWAP-7741", status_code=404)

        self.client.post(
            reverse("listing_edit", args=[listing.pk]),
            {
                "title": "stolen",
                "description": "nope",
                "price": "1.00",
                "category": "other",
                "seller_note": "hacked",
            },
        )
        self.client.post(reverse("listing_sold", args=[listing.pk]))
        self.client.post(reverse("listing_delete", args=[listing.pk]))
        listing.refresh_from_db()
        self.assertEqual(listing.title, "67W USB-C charger")
        self.assertEqual(listing.status, "available")
        self.assertIn("SWAP-7741", listing.seller_note)

        detail = self.client.get(reverse("listing_detail", args=[listing.pk]))
        self.assertContains(detail, "Message seller")
        self.assertNotContains(detail, "Edit listing")
        self.assertNotContains(detail, "Mark sold")

        before = Message.objects.filter(thread=thread).count()
        thread_page = self.client.get(reverse("thread_detail", args=[thread.pk]))
        self.assertEqual(thread_page.status_code, 404)
        self.client.post(reverse("thread_detail", args=[thread.pk]), {"body": "intruder"})
        self.assertEqual(Message.objects.filter(thread=thread).count(), before)

        self.client.logout()
        denied = self.client.post(reverse("listing_sold", args=[listing.pk]))
        self.assertEqual(denied.status_code, 302)
        self.assertIn("/login/", denied.url)

    def test_buyer_and_seller_can_message(self):
        textbook = Listing.objects.get(title="CPEG 470 textbook, 3rd ed")
        self.assertTrue(self.client.login(username="alex", password="campus123"))
        started = self.client.get(reverse("start_thread", args=[textbook.pk]))
        thread = Thread.objects.get(listing=textbook, buyer__username="alex")
        self.assertRedirects(started, reverse("thread_detail", args=[thread.pk]))
        self.client.post(reverse("thread_detail", args=[thread.pk]), {"body": "Is chapter 2 clean?"})

        self.client.logout()
        self.assertTrue(self.client.login(username="jordan", password="campus123"))
        page = self.client.get(reverse("thread_detail", args=[thread.pk]))
        self.assertContains(page, "Is chapter 2 clean?")
        self.client.post(reverse("thread_detail", args=[thread.pk]), {"body": "Yes, mostly."})

        bike = Thread.objects.get(listing__title="Campus bike, blue frame")
        self.assertContains(self.client.get(reverse("thread_detail", args=[bike.pk])), "Perkins racks")
        self.assertContains(self.client.get(reverse("mine")), "Campus bike, blue frame")

    def test_profile_cannot_grant_staff_and_desk_stays_closed(self):
        self.assertEqual(ProfileForm.Meta.fields, ["first_name", "last_name", "email"])
        self.assertTrue(self.client.login(username="jordan", password="campus123"))
        page = self.client.get(reverse("profile"))
        self.assertNotContains(page, "is_staff")
        self.assertNotContains(page, "Show my name on the department board")

        self.client.post(
            reverse("profile"),
            {
                "first_name": "Jordan",
                "last_name": "Park",
                "email": "jordan.park@campus.edu",
                "is_staff": "on",
                "is_superuser": "on",
            },
        )
        jordan = User.objects.get(username="jordan")
        self.assertEqual(jordan.first_name, "Jordan")
        self.assertEqual(jordan.email, "jordan.park@campus.edu")
        self.assertFalse(jordan.is_staff)
        self.assertFalse(jordan.is_superuser)

        desk = self.client.get(reverse("desk"))
        self.assertContains(desk, "This page is for department board accounts.")
        self.assertNotContains(desk, "DESK-2290")

        dean = User.objects.create_user("dean", "dean@campus.edu", "campus123", is_staff=True)
        self.client.force_login(dean)
        staff_desk = self.client.get(reverse("desk"))
        self.assertContains(staff_desk, "DESK-2290")

    def test_register_and_sign_in(self):
        registered = self.client.post(
            reverse("register"),
            {
                "username": "riley",
                "password1": "ShelfBoard-99",
                "password2": "ShelfBoard-99",
            },
        )
        self.assertRedirects(registered, reverse("home"))
        self.assertEqual(User.objects.get(username="riley").is_staff, False)
        self.client.post(reverse("logout"))
        mine = self.client.get(reverse("mine"))
        self.assertEqual(mine.status_code, 302)
        self.assertIn("/login/", mine.url)

        signed_in = self.client.post(
            reverse("sign_in"),
            {"username": "riley", "password": "ShelfBoard-99"},
        )
        self.assertRedirects(signed_in, reverse("home"))
        self.assertContains(self.client.get(reverse("mine")), "You have not posted yet.")
