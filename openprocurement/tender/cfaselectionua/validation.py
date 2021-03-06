# -*- coding: utf-8 -*-
from iso8601 import parse_date

from openprocurement.api.utils import error_handler, raise_operation_error, get_now
from openprocurement.api.validation import OPERATIONS, validate_data, validate_json_data

from openprocurement.tender.cfaselectionua.constants import TENDER_PERIOD_MINIMAL_DURATION
from openprocurement.tender.core.utils import calculate_business_date


def validate_patch_tender_data(request):
    data = validate_json_data(request)
    return validate_data(request, type(request.tender), True, data)


# tender documents
def validate_document_operation_in_not_allowed_tender_status(request):
    if request.authenticated_role != 'auction' and request.validated['tender_status'] not in ['draft.pending', 'active.enquiries'] or \
       request.authenticated_role == 'auction' and request.validated['tender_status'] not in ['active.auction', 'active.qualification']:
        raise_operation_error(request, 'Can\'t {} document in current ({}) tender status'.format(OPERATIONS.get(request.method), request.validated['tender_status']))


#bids
def validate_view_bids(request):
    if request.validated['tender_status'] in ['active.tendering', 'active.auction']:
        raise_operation_error(request, 'Can\'t view {} in current ({}) tender status'.format('bid' if request.matchdict.get('bid_id') else 'bids', request.validated['tender_status']))


def validate_update_bid_status(request):
    if request.authenticated_role != 'Administrator':
        bid_status_to = request.validated['data'].get("status")
        if bid_status_to != request.context.status and bid_status_to != "active":
            request.errors.add('body', 'bid', 'Can\'t update bid to ({}) status'.format(bid_status_to))
            request.errors.status = 403
            raise error_handler(request.errors)


# bid documents
def validate_view_bid_document(request):
    if request.validated['tender_status'] in ['active.tendering', 'active.auction'] and request.authenticated_role != 'bid_owner':
        raise_operation_error(request, 'Can\'t view bid {} in current ({}) tender status'.format('document' if request.matchdict.get('document_id') else 'documents', request.validated['tender_status']))


def get_supplier_contract(contracts, tenderers):
    for contract in contracts:
        if contract.status != 'active':
            continue
        for supplier in contract.suppliers:
            for tenderer in tenderers:
                if supplier.identifier.id == tenderer.identifier.id:
                    return contract


def validate_bid(request):
    if request.method == 'POST':
        bid = request.validated['bid']
    elif request.method == 'PATCH':
        bid_class = request.context.__class__
        bid = bid_class(request.validated['data'])
    contracts = request.validated['tender'].agreements[0].contracts

    supplier_contract = get_supplier_contract(contracts, bid.tenderers)

    if not supplier_contract:
        raise_operation_error(request, 'Bid is not a member of agreement')

    if bid.lotValues and supplier_contract.value and bid.lotValues[0].value.amount > supplier_contract.value.amount:
        raise_operation_error(request, 'Bid value.amount can\'t be greater than contact value.amount.')

    contract_parameters = {(p.code, p.value) for p in supplier_contract.parameters}
    bid_parameters = {(p.code, p.value) for p in bid.parameters}
    if not bid_parameters.issubset(contract_parameters):
        raise_operation_error(request, 'Can\'t post inconsistent bid')


def validate_bid_document_operation_in_not_allowed_tender_status(request):
    if request.validated['tender_status'] not in ['active.tendering', 'active.qualification']:
        raise_operation_error(request, 'Can\'t {} document in current ({}) tender status'.format(OPERATIONS.get(request.method), request.validated['tender_status']))


def validate_bid_document_operation_with_not_pending_award(request):
    if request.validated['tender_status'] == 'active.qualification' and not [i for i in request.validated['tender'].awards if i.status == 'pending' and i.bid_id == request.validated['bid_id']]:
        raise_operation_error(request, 'Can\'t {} document because award of bid is not in pending state'.format(OPERATIONS.get(request.method)))


# lot
def validate_lot_operation(request):
    tender = request.validated['tender']
    if tender.status not in ['draft.pending', 'active.enquiries']:
        raise_operation_error(request, 'Can\'t {} lot in current ({}) tender status'.format(OPERATIONS.get(request.method), tender.status))


# auction
def validate_auction_info_view(request):
    if request.validated['tender_status'] != 'active.auction':
        raise_operation_error(request, 'Can\'t get auction info in current ({}) tender status'.format(request.validated['tender_status']))


# award
def validate_create_award_not_in_allowed_period(request):
    tender = request.validated['tender']
    if tender.status != 'active.qualification':
        raise_operation_error(request, 'Can\'t create award in current ({}) tender status'.format(tender.status))


def validate_create_award_only_for_active_lot(request):
    tender = request.validated['tender']
    award = request.validated['award']
    if any([i.status != 'active' for i in tender.lots if i.id == award.lotID]):
        raise_operation_error(request, 'Can create award only in active lot status')


# award complaint
def validate_award_complaint_update_not_in_allowed_status(request):
    if request.context.status not in ['draft', 'claim', 'answered']:
        raise_operation_error(request, 'Can\'t update complaint in current ({}) status'.format(request.context.status))


# award document


def validate_award_document(request):
    operation = OPERATIONS.get(request.method)
    if request.validated['tender_status'] != 'active.qualification':
        raise_operation_error(request, 'Can\'t {} document in current ({}) tender status'.format(
            operation, request.validated['tender_status']))
    if any([i.status != 'active' for i in request.validated['tender'].lots if
            i.id == request.validated['award'].lotID]):
        raise_operation_error(request, 'Can {} document only in active lot status'.format(operation))
    if operation == 'update' and request.authenticated_role != (request.context.author or 'tender_owner'):
        request.errors.add('url', 'role', 'Can update document only author')
        request.errors.status = 403
        raise error_handler(request.errors)


# contract document
def validate_cancellation_document_operation_not_in_allowed_status(request):
    if request.validated['tender_status'] in ['complete', 'cancelled', 'unsuccessful']:
        raise_operation_error(request, 'Can\'t {} document in current ({}) tender status'.format(OPERATIONS.get(request.method), request.validated['tender_status']))


# patch agreement
def validate_agreement_operation_not_in_allowed_status(request):
    if request.validated['tender_status'] != 'draft.pending':
        raise_operation_error(request,
                              'Can\'t {} agreement in current ({}) tender status'.format(
                                  OPERATIONS.get(request.method), request.validated['tender_status']))


def validate_patch_agreement_data(request):
    model = type(request.tender).agreements.model_class
    return validate_data(request, model, True)


# tender
def validate_patch_tender_in_draft_pending(request):
    if request.validated['tender_src']['status'] == 'draft.pending' and \
            request.authenticated_role not in ('agreement_selection', 'Administrator'):
        raise_operation_error(request,
                              'Can\'t {} tender in current ({}) tender status'.format(
                                  OPERATIONS.get(request.method), request.validated['tender_status']))


def validate_patch_tender_bot_only_in_draft_pending(request):
    if request.authenticated_role == 'agreement_selection' and \
            request.validated['tender_src']['status'] != 'draft.pending':
        raise_operation_error(request,
                              'Can\'t {} tender in current ({}) tender status'.format(
                                  OPERATIONS.get(request.method), request.validated['tender_status']))


def validate_tender_status_update_in_terminated_status(request):
    tender = request.context
    if request.authenticated_role != 'Administrator' and \
            tender.status in ('complete', 'unsuccessful', 'cancelled', 'draft.unsuccessful'):
        raise_operation_error(request, 'Can\'t update tender in current ({}) status'.format(tender.status))


def validate_json_data_in_active_enquiries(request):
    source = request.validated['data']
    tender = request.validated['tender_src']
    data = source
    if 'tenderPeriod' in source and 'endDate' in source['tenderPeriod']:
        validate_patch_tender_tenderPeriod(request)
        data['tenderPeriod'] = {
            'endDate': source['tenderPeriod']['endDate']
        }

    if len(source['items']) != len(tender['items']):
        raise_operation_error(request, 'Can\'t update tender items. Items count mismatch')
    if [item['id'] for item in source['items']] != [item['id'] for item in tender['items']]:
        raise_operation_error(request, 'Can\'t update tender items. Items order mismatch')

    request.validated['data'] = data


def validate_patch_tender_tenderPeriod(request):
    source = request.validated['data']
    tender = request.validated['tender_src']
    startDate = tender['tenderPeriod'].get('startDate')
    endDate = source['tenderPeriod'].get('endDate')

    if (startDate and endDate) and \
            calculate_business_date(parse_date(startDate), request.content_configurator.tender_period, tender) > parse_date(endDate):
        raise_operation_error(request, 'tenderPeriod should last at least 3 days')
