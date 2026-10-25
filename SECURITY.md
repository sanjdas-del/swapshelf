# SwapShelf: architecture and the authorization patch

SwapShelf is a campus buy/sell board. A student posts a listing, the public board shows it, another student messages them, and the seller marks it sold. A private seller note can hold a pickup detail that is not part of the public description. The department desk holds a separate note for staff accounts.

Two checks in the uploaded views and forms were missing. Any signed-in student could open, edit, sell, or remove somebody else's listing and could read or write any message thread. The profile form also wrote Django's `is_staff` bit, so the same student could open the department desk. This repo is the patched app. Posting, editing your own listing, marking it sold, messaging the other party, registration, and sign-in still work.

## Architecture

```
Browser
  |  session cookie (Django session, HttpOnly)
  v
Django (market/views.py)
  home, listing detail          public
  register, sign in, sign out   public; sign-out is POST
  post, edit, sold, remove      login + listing.owner
  message thread                login + buyer or listing owner
  profile                       login; writes name and email only
  desk                          login + is_staff
  v
SQLite (data/swapshelf.db)
  auth_user, market_listing, market_thread, market_message
```

Passwords are Django password hashes. `UserCreationForm` and `AuthenticationForm` handle register and sign-in. State-changing forms use Django's CSRF token.

### How a listing id becomes a row

The board links to `/listings/<pk>/`. `listing_detail` loads that primary key and no other condition:

```python
def listing_detail(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
```

`pk` is the `market_listing.id` column. The row's `owner_id` points at `auth_user`. The public template renders title, description, price, category, status, and the seller's name. It does not render `seller_note`.

The same integer is reused for the edit, sold, remove, and "message seller" routes. Edit and sold used to load the row with that id alone. They now also require `owner=request.user`. "Message seller" still loads any listing, then creates a thread whose buyer is the signed-in user. Opening a thread requires that user to be the buyer or the listing owner.

Home is `Listing.objects.exclude(status="removed")`, optionally filtered with `?category=`. Sold rows stay on the board. The category value is a bound query parameter, not SQL text.

### Which pages a logged-out visitor can open

| Request | Who |
| --- | --- |
| `GET /` | Anyone. Public cards, no seller notes. |
| `GET /listings/<pk>/` | Anyone. Public description only. |
| `GET /login/`, `POST /login/` | Anyone. |
| `GET /register/`, `POST /register/` | Anyone. A new account is not staff. |
| `POST /logout/` | Anyone. Clears the session. |

`GET /listings/new/`, edit, sold, remove, `/me/`, threads, profile, and `/desk/` are wrapped in `login_required` and redirect to `/login/`. Sold, remove, and sign-out also require POST.

### What the profile form writes back to the user

The profile view binds the form to `request.user` and saves that same row. It never takes a user id from the query string.

The uploaded form wrote four fields:

```python
class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "is_staff"]
        labels = {
            "is_staff": "Show my name on the department board",
        }
```

`first_name`, `last_name`, and `email` are the name and address shown on listings. `is_staff` is Django's staff flag. The label called it a department-board opt-in. The desk does not list names, so the checkbox did not do what it said. Saving the form with the box checked set `User.is_staff = True` on the signed-in account.

The patched form only includes `first_name`, `last_name`, and `email`. The view also puts the previous `is_staff` and `is_superuser` values back before it saves, so a posted `is_staff=on` or `is_superuser=on` does not stick.

### What the department desk is for, and who can open it

`/desk/` is the department hold closet note (reimbursement code included). It is not a second public board.

```python
@login_required
def desk(request):
    if not request.user.is_staff:
        return render(request, "market/desk.html", {"allowed": False})
    return render(
        request,
        "market/desk.html",
        {
            "allowed": True,
            "note": "Department hold closet, Hullihen basement cage B. Reimbursement code DESK-2290. Not for the public board.",
        },
    )
```

A signed-in student who is not staff gets "This page is for department board accounts." and does not receive the note. The nav link is rendered only when `user.is_staff`. The desk check itself was already the right gate. The hole was the profile form turning that flag on.

Staff has to be set outside the profile page (the admin user, or `is_staff=True` on the account). Django admin is mounted at `/admin/` and uses the same flag. Demo accounts are not staff.

## The defect

Two bugs in the uploaded views and forms. Either one is enough to read a note that is not on the public board.

### 1. Listing and thread ids were not checked against the account

Edit, mark sold, and remove loaded any listing:

```python
@login_required
def listing_edit(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    form = ListingForm(request.POST or None, instance=listing)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("listing_detail", pk=listing.pk)
    return render(request, "market/form.html", {"form": form, "heading": "Edit listing", "listing": listing})


@login_required
@require_POST
def listing_sold(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    listing.status = "sold"
    listing.save(update_fields=["status"])
    return redirect("listing_detail", pk=listing.pk)
```

Remove did the same lookup and set `status = "removed"`. The edit form includes `seller_note`, which the public listing page does not. The detail template also offered Edit and Mark sold to every signed-in visitor, not only the owner.

Threads had the same shape. Any signed-in user could read the messages and append one:

```python
@login_required
def thread_detail(request, pk):
    thread = get_object_or_404(Thread.objects.select_related("listing", "buyer", "listing__owner"), pk=pk)
    if request.method == "POST":
        body = (request.POST.get("body") or "").strip()
        if body:
            Message.objects.create(thread=thread, sender=request.user, body=body)
        return redirect("thread_detail", pk=thread.pk)
```

**How to trigger it on the unpatched app**

1. Sign in as `jordan` / `campus123`.
2. Open Alex's charger on the board and note the id, for example `/listings/1/`.
3. Open `/listings/1/edit/`. The form's seller note is: `East vestibule locker 14, code SWAP-7741. Text when you are downstairs.`
4. `POST /listings/1/sold/` marks Alex's charger sold. `POST /listings/1/delete/` takes it off the board.
5. Sign in as `sam` / `foundit!` (Sam is not on the bike thread). Open `/threads/1/`. The page shows Jordan and Alex's messages about the bike. Sam can POST a reply into that thread.

The bike message says the lock code is on the seller note, not in the thread. Reading the thread does not reveal `SWAP-7741`. The edit form does.

### 2. The profile form granted staff

The profile checkbox was `is_staff` under the label "Show my name on the department board". `profile` called `form.save()` on `request.user`.

**How to trigger it on the unpatched app**

1. Register an account, or sign in as `sam` / `foundit!`. Sam is not staff. `/desk/` shows only "This page is for department board accounts."
2. Open `/profile/`, check "Show my name on the department board", and save. The POST body includes `is_staff=on`.
3. Open `/desk/`. The page now includes `Department hold closet, Hullihen basement cage B. Reimbursement code DESK-2290.`
4. The same session can open `/admin/`, because Django treats `is_staff` as access to the admin site.

Checking the box does not change another user's row. It changes the signed-in user's privileges. That is still the bug: the field is not a display preference.

The desk view was not open to every account. A student who never set `is_staff` did not receive the note. The profile form was how they set it.

## The patch

- `listing_edit`, `listing_sold`, and `listing_delete` load with `owner=request.user`. A miss is a 404. The listing is not changed.
- `thread_detail` loads the thread only when `buyer` is the user or `listing.owner` is the user. Anyone else gets a 404, including on POST, so they cannot insert a message.
- The listing page shows Edit and Mark sold only when `user == listing.owner`. Message seller stays available to any signed-in student. The server checks are what stop a direct POST.
- `ProfileForm` fields are `first_name`, `last_name`, and `email`. `profile` copies `is_staff` and `is_superuser` from the row before save and writes those values back.
- The desk view is unchanged. Non-staff still see the denial line. Staff still see the closet note.

What still works: register, sign in, sign out, the public category filter, posting a listing, editing and marking sold as the owner, the owner reading their own seller note, and a buyer/seller thread. Starting a thread on someone else's listing is the message-seller action and is still allowed.

`python manage.py test` covers the seller note staying off the public listing, Jordan's failure to edit or sell Alex's charger, Sam's failure to read the bike thread, Alex posting and marking a new listing sold, both sides of a new thread, a profile POST that includes `is_staff` and `is_superuser`, the closed desk, a real staff account opening the desk, and register plus sign-in.
