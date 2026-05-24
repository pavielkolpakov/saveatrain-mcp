# MCP Server Design Notes — Save a Train Vendor API

Reference doc for building an MCP server that wraps the SAT Rails vendor API so LLM agents can search trains, build bookings, confirm payments via natural language.

All endpoints under `/api/v1/`. JSON in/out. Token auth via headers.

---

## 1. Authentication

All API calls run `authenticate_agent!` in `app/controllers/api/v1/base_controller.rb:16-35`.

**Required headers on every request:**
- `X-Agent-Email` - sales agent email
- `X-Agent-Token` - bearer token
- `X-Forwarded-For` - client IP (IP whitelist check, except dashboard)
- `Accept: application/json`

Failure: HTTP 401 `{"errors": "X-Agent-Token is invalid or expired"}`.
Auth validates: agent active, token valid/unexpired, IP whitelisted, request domain matches.

---

## 2. Core Booking Flow (in order)

| # | Method | Path | Controller#action | Purpose |
|---|--------|------|-------------------|---------|
| 1 | POST | `/api/v1/searches` | `SearchesController#create` | Create search, fetch outbound results |
| 2 | POST | `/api/v1/searches/{identifier}/inbound_search` | `SearchesController#inbound_search` | Fetch inbound results (round trip) |
| 3 | GET  | `/api/v1/searches/{identifier}/results/{id}/sub_routes` | `Searches::ResultsController#sub_routes` | Legs/transfers/fares for a result |
| 4 | GET  | `/api/v1/searches/{identifier}/results/{id}/tariff_conditions/{result_fare_id}` | `Searches::ResultsController#tariff_conditions` | Cancellation/exchange rules |
| 5 | POST | `/api/v1/searches/{identifier}/confirm_selection` | `SearchesController#confirm_selection` | Lock outbound/inbound, returns seat opts + required booking fields |
| 6 | POST | `/api/v1/bookings` | `BookingsController#create` | Build booking w/ passengers, returns total price |
| 7 | POST | `/api/v1/bookings/confirm` | `BookingsController#confirm` | Finalize w/ provider, returns PNR |

Routes file: `config/routes.rb:29-44`.

---

## 3. Supporting Endpoints

### Search helpers
- `POST /api/v1/searches/new_outbound_results` - paginate earlier/later outbound (`SearchesController#new_outbound_results`, routes.rb:36)
- `POST /api/v1/searches/new_inbound_results` - same for inbound (routes.rb:37)
- `POST /api/v1/searches/origin_and_destination_search` - station autocomplete (`searches_controller.rb:26-35`)
- `POST /api/v1/searches/popular_routes` - trending routes (`searches_controller.rb:37-46`)
- `GET  /api/v1/vendor_stations` - all searchable stations (`vendor_stations_controller.rb:1-12`)
- `POST /api/v1/routes/valid` - validate route exists (routes.rb:30)
- `GET  /api/v1/routes/valid` - routes with historic results (routes.rb:31)
- `GET  /api/v1/fare_class_mapper` - map provider fare names to standard classes (routes.rb:32)
- `GET  /api/v1/reduction_codes` - list discount codes (routes.rb:84)
- `GET  /api/v1/bookings/currencys` - supported currencies (routes.rb:42)

### Post-booking
- `GET  /api/v1/bookings/{id}` - retrieve order by search identifier
- `POST /api/v1/order_info` - full order details by identifier + email (`order_info_controller.rb`)
- `GET  /api/v1/bookings/{id}/image` - confirmation image
- `POST /api/v1/bookings/{id}/apply_voucher/{voucher_code}` - apply discount
- `POST /api/v1/bookings/{id}/additional_params` - provider-specific extras
- `POST /api/v1/bookings/submit_payment` - Adyen payment
- `POST /api/v1/bookings/change_traveller` - update passenger details
- `POST /api/v1/manage_bookings` - legacy order lookup

### Cancellation
- `POST /api/v1/bookings/cancellation` - initiate refund
- `POST /api/v1/bookings/confirm_cancellation` - confirm refund

### Fare change (modify existing booking)
- `POST /api/v1/bookings/fare_change_search`
- `POST /api/v1/bookings/fare_change_inbound_search`
- `POST /api/v1/bookings/fare_change_select`
- `POST /api/v1/bookings/fare_change_confirm`

### Station change
- `POST /api/v1/bookings/station_change_search`
- `POST /api/v1/bookings/station_change_inbound`
- `POST /api/v1/bookings/station_change_select`
- `POST /api/v1/bookings/station_change_confirm`

---

## 4. Request/Response Shapes

### POST /api/v1/searches
Params (`searches_controller.rb:90-108`):
```json
{
  "search": {
    "departure_datetime": "2020-03-12 10:00",
    "return_departure_datetime": "2020-04-12 10:00",
    "route_attributes": {
      "origin_station_attributes": { "uid": "SAT_OXQJY" },
      "destination_station_attributes": { "uid": "SAT_OTWZL" }
    },
    "searches_passengers_attributes": {
      "0": { "age": null, "passenger_type_attributes": { "type": "Search::PassengerType::Adult" } },
      "1": { "age": 10, "passenger_type_attributes": { "type": "Search::PassengerType::Youth" } }
    }
  }
}
```
Response (`search_serializer.rb:1-58`):
```json
{
  "identifier": "vAa4xK",
  "complete": true,
  "route": { "origin_station": {...}, "destination_station": {...} },
  "departure_datetime": "...",
  "return_departure_datetime": "...",
  "expiration_time_left": 1800,
  "is_beginning": true,
  "is_ending": false,
  "results": [
    {
      "id": 777,
      "identifier": "830001700,...",
      "departure_datetime": "...",
      "arrival_datetime": "...",
      "duration": 179,
      "best_price": 17.7,
      "selected": false,
      "provider": { "name": "Nsi" },
      "changes_count": 2
    }
  ]
}
```

### POST /api/v1/searches/{identifier}/confirm_selection
Params (`searches_controller.rb:111-120`):
```json
{
  "select_results_attributes": {
    "search_identifier": "vAa4xK",
    "result_id": 777,
    "transfers_attributes": [ { "id": 0, "fare_id": 123 } ]
  }
}
```
Response (`confirm_selection_serializer.rb:1-52`):
```json
{
  "search_identifier": "vAa4xK",
  "outbound_selected_result": {
    "id": 777, "departure_datetime": "...", "arrival_datetime": "...",
    "duration": 179, "best_price": 17.7,
    "seat_preference": {
      "currency": "EUR", "amount": 15.0, "status": "available",
      "options": [
        { "code": "ALLOWED_SPACE_TYPE.DS", "name": "Double Seat", "description": "..." }
      ]
    }
  },
  "inbound_selected_result": {...},
  "booking_required_params_type": "N",
  "booking_required_params": {
    "order_customer_attributes": ["email","fname","lname","gender","mobile"],
    "passengers_attributes": ["title","fname","lname","birthdate","country","passenger_type_attributes"]
  }
}
```

### POST /api/v1/bookings
Params (`bookings_controller.rb:244-280`):
```json
{
  "booking": {
    "search_identifier": "vAa4xK",
    "order_customer_attributes": {
      "email":"test@gmail.com","fname":"Timo","lname":"Mossi","gender":"M",
      "mobile":"+33123456789","address":"123 Rue","country":"FR","city":"Paris","postcode":"75000"
    },
    "passengers_attributes": {
      "0": {
        "title":"Mr","fname":"Timo","lname":"Mossi","birthdate":"1974-11-19",
        "country":"CA","nationality":"CA","gender":"M",
        "passport_number":"AB123456","id_type":"passport","id_number":"AB123456","id_expiry":"2030-12-31",
        "passenger_type_attributes": { "type":"Search::PassengerType::Adult" }
      }
    },
    "seat_preference_attributes": {
      "seat_preference_outbound": "ALLOWED_SPACE_TYPE.DS",
      "seat_preference_inbound": "ALLOWED_SPACE_TYPE.DS"
    },
    "discount_code": "SAVE10"
  }
}
```
Response (`order_summary_serializer.rb:1-86`):
```json
{
  "search_identifier": "vAa4xK",
  "outbound_trip_info": {
    "origin_station_info": [...], "destination_station_info": [...],
    "departure": "...", "arrival": "...", "trip_duration": 179, "fare": "Second Class"
  },
  "inbound_trip_info": {...},
  "price": 17.7,
  "outbound_seat_reservation_fee": 15.0,
  "inbound_seat_reservation_fee": 15.0,
  "total_price": 47.7
}
```

### POST /api/v1/bookings/confirm
Params (`bookings_controller.rb:283-288`):
```json
{ "booking": { "search_identifier": "vAa4xK", "affiliate_id": "partner123" } }
```
Response (`booking_confirmation_serializer.rb`):
```json
{
  "search_identifier": "vAa4xK",
  "pnr": "GPQHLMF",
  "progress_status": "confirmed",
  "order_id": 12345,
  "outbound_trip_info": {...}, "inbound_trip_info": {...},
  "total_price": 47.7,
  "outbound_seat_reservation_fee": 15.0,
  "inbound_seat_reservation_fee": 15.0
}
```

### GET /api/v1/searches/{id}/results/{rid}/sub_routes
Response (sample `spec/support/api/files/nsi_sub_routes_response.json:1-126`):
```json
{
  "status": "success",
  "data": {
    "legs": [
      {
        "id": "leg_...",
        "modality": { "type":"train","name":"Thalys","code":"THA","number":"9327",
                      "facilities":[{"name":"Bar","code":"BW"}] },
        "duration": { "days":0,"hours":1,"minutes":22,"delay":false },
        "origin": { "name":"Paris Nord","country":"FR","code":"FRPNO",
                    "departure":{"planned":"2020-03-11 10:00","delay":0,"platform":null} },
        "destination": { "name":"Bruxelles Midi","country":"BE","code":"BEBMI",
                         "arrival":{"planned":"...","delay":0,"platform":"3"} },
        "seating": { "reservation":"included","preferences":[] }
      }
    ]
  }
}
```

### POST /api/v1/order_info
Response (`order_info_controller.rb:80-101`):
```json
{
  "identifier": "vAa4xK",
  "outbound_trip_info": {...}, "inbound_trip_info": {...},
  "provider": "Order::Nsi",
  "placed_on": "Feb 24, 14:30",
  "price": 17.7,
  "outbound_seat_reservation_fee": 15.0,
  "inbound_seat_reservation_fee": 15.0,
  "total_price": 47.7,
  "order_status": "confirmed",
  "order_email": "test@gmail.com",
  "order_phone": "+33...",
  "voucher": { "code":"SAVE10","before_price":50.0,"after_price":47.7 },
  "pnr": "GPQHLMF",
  "passengers": [{...}],
  "is_failed": false,
  "image_url": "https://...",
  "eurail_details": null
}
```

### GET /api/v1/vendor_stations
```json
[
  {
    "id": 1, "uid": "SAT_OXQJY", "state": "searchable", "original_name": "Paris",
    "station_search_names": [
      { "name":"Paris (All Stations)","language":{"value":"en","name":"English"} }
    ],
    "station_provider_params": [
      { "provider_id":1,"provider_name":"Nsi","station_code":"FRPNO","native_name":"Paris" }
    ]
  }
]
```

---

## 5. Domain Models

### Search (`app/models/search.rb`)
`identifier` (6-char code, e.g. "vAa4xK"), `departure_datetime`, `return_departure_datetime` (null = one-way), `route_id`, `complete`, `expiration_time_left`. Has many results, has one booking.

### Booking + Order (`app/models/booking.rb`, `app/models/order.rb`)
Booking joins Search -> Order. Order is STI: `Order::Nsi`, `Order::Trenitalia`, `Order::Gate`, `Order::Acp`, `Order::Eurail`.
Order fields: `price`, `outbound_seat_reservation_fee`, `inbound_seat_reservation_fee`, `total_price`, `progress_status` (pending -> confirmed -> completed/failed/expired/canceled), `pnr`, `voucher_id`.

### Order::Customer (`app/models/order/customer.rb`)
`fname`, `lname`, `email`, `gender` (M/F), `mobile_number`, `address`, `country`, `city`, `postcode`.

### Passenger (`app/models/passenger.rb`)
`title`, `fname`, `lname`, `birthdate`, `country`, `nationality`, `birth_country`, `passport_number`, `gender`, `id_type` (passport/id_card/driving_license), `id_number`, `id_expiry`, `type` (STI: Adult/Youth/Senior).

### Station (`app/models/station.rb`)
`uid` (e.g. "SAT_OXQJY"), `state` (searchable/routable/inactive), `original_name`, has many `station_search_names` (multilingual) and `station_provider_params` (per-provider codes).

### Route (`app/models/route.rb`)
`origin_station_id`, `destination_station_id`.

### Result (`app/models/result.rb`)
STI per provider. `identifier`, `departure_datetime`, `arrival_datetime`, `duration` (min), `best_price`, `selected`, `kind_of` (outbound/inbound), `changes_count`. Has many `result_sub_routes`, has one `seat_preference`.

### Result::SubRoute (`app/models/result/sub_route.rb`)
A leg. Has many `result_transfers`, `result_fares`.

### Result::Fare (`app/models/result/fare.rb`)
STI per provider. `name` (e.g. "First Class"), `total_price`, `selected`, `selected_partially`, `nsi_offer_identifier`.

### Result::SeatPreference (`app/models/result/seat_preference.rb`)
`currency`, `amount`, `status`. Options: `[{code, name, description}]` (e.g. `ALLOWED_SPACE_TYPE.DS`).

### Provider (`app/models/provider.rb`)
`name` in {`Nsi`, `Trenitalia`, `Gate`, `Acp`}.

### Search::PassengerType
Class names used in API: `Search::PassengerType::Adult`, `::Youth`, `::Senior`, `::Child`, `::Infant`.

---

## 6. Providers

**Provider selection is automatic.** Searches query all providers for the route; each result has `provider.name`. Booking flow auto-routes to the right provider handler based on selected result (`operation_process/bookings_management.rb:12-17`).

**Per-provider quirks:**
- **NSI/Benerail** - Seat reservation separately charged. `seat_preference_attributes` required in booking (use `"notreserve"`, null, or seat code).
- **Trenitalia** - Accepts `discount_code` (NSI ignores). May need additional params via `additional_params` endpoint.
- **Gate / ACP** - Provider-specific validators; may require extra fields.
- **Eurail** - Pass products, different flow (uses carts, not results/sub_routes). `Order::Eurail`.

**Cross-provider features:** cancellation, fare change, station change, traveller update, vouchers (per-provider compatibility varies).

---

## 7. README / Local Setup

```bash
cp .env.example .env
docker-compose up --build
```
PostgreSQL `sat_vendor_api_development`. Rails API mode. Sidekiq for background jobs. Sentry. Faraday for provider HTTP.

DB restore: `cat dump.sql | docker exec -i sat-vendor-api-db-1 psql -U postgres -d sat_vendor_api_development`

---

## 8. Error Handling

- 401 - auth failure: `{"errors": "<message>"}`
- 422 - validation failure: `{"errors": {...}}`
- 500 - server error: generic message

Always check status code and presence of `errors` key.

---

## 9. Minimal MCP Tool Set (suggested)

Map endpoints to MCP tools agents can call:

1. `search_stations(query)` -> `POST /searches/origin_and_destination_search`
2. `list_stations()` -> `GET /vendor_stations`
3. `search_trains(origin_uid, destination_uid, departure_datetime, return_datetime?, passengers[])` -> `POST /searches`
4. `search_inbound(search_identifier, outbound_selection)` -> `POST /searches/{id}/inbound_search`
5. `get_sub_routes(search_identifier, result_id)` -> `GET .../sub_routes`
6. `get_tariff_conditions(search_identifier, result_id, fare_id)` -> `GET .../tariff_conditions/{fare_id}`
7. `confirm_selection(search_identifier, result_id, fare_selections)` -> `POST .../confirm_selection`
8. `create_booking(search_identifier, customer, passengers, seat_preferences, discount_code?)` -> `POST /bookings`
9. `confirm_booking(search_identifier, affiliate_id?)` -> `POST /bookings/confirm`
10. `get_order(search_identifier, email)` -> `POST /order_info`
11. `cancel_booking(search_identifier)` -> `POST /bookings/cancellation` then `/confirm_cancellation`
12. `change_traveller(...)`, `apply_voucher(...)`, `submit_payment(...)` etc.

**Critical state to track per conversation:** `search_identifier` (drives everything post-search), `expiration_time_left` (searches expire ~30 min), `booking_required_params` (provider-specific fields returned by confirm_selection — tool 8 must adapt).

---

## 10. Files to Reference

- Routes: `config/routes.rb`
- Auth: `app/controllers/api/v1/base_controller.rb`
- Search controller: `app/controllers/api/v1/searches_controller.rb`
- Bookings controller: `app/controllers/api/v1/bookings_controller.rb`
- Order info: `app/controllers/api/v1/order_info_controller.rb`
- Serializers: `app/serializers/api/v1/`
- Sample responses: `spec/support/api/files/`
- Provider routing logic: `app/operators/operation_process/bookings_management.rb`
- Project conventions: `CLAUDE.md`, `app/controllers/CLAUDE.md`, `app/operators/operation_process/CLAUDE.md`
