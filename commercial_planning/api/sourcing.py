"""Whitelisted v2 sourcing actions. Each returns the refreshed sourcing view plus the action's result."""

import json

import frappe

from commercial_planning.services import sourcing


def parse_list(value):
	return json.loads(value) if isinstance(value, str) else (value or [])


def respond(version, result=None):
	return {"result": result, "sourcing": sourcing.get_sourcing(version)}


@frappe.whitelist()
def get_sourcing(version):
	return sourcing.get_sourcing(version)


@frappe.whitelist()
def get_quotation_state(version):
	return sourcing.quotation_info(version)


@frappe.whitelist(methods=["POST"])
def send_rfq(version, rows, suppliers, message=None):
	return respond(version, sourcing.send_rfq(version, parse_list(rows), parse_list(suppliers), message))


@frappe.whitelist(methods=["POST"])
def pull_quotes(version):
	return respond(version, sourcing.pull_quotes(version))


@frappe.whitelist()
def bid_form(version, rfq, supplier, revise=None):
	return sourcing.bid_form(version, rfq, supplier, revise or None)


@frappe.whitelist(methods=["POST"])
def enter_bid(version, rfq, supplier, rates, valid_till=None, submit=0, revise=None):
	rates = json.loads(rates) if isinstance(rates, str) else rates
	return respond(version, sourcing.enter_bid(version, rfq, supplier, rates, valid_till or None, frappe.utils.cint(submit), revise or None))


@frappe.whitelist(methods=["POST"])
def select_quote(version, row_key, supplier_quotation):
	return respond(version, sourcing.select_quote(version, row_key, supplier_quotation))


@frappe.whitelist(methods=["POST"])
def create_purchase_orders(version, submit=0, supplier=None):
	return respond(version, sourcing.create_purchase_orders(version, frappe.utils.cint(submit), supplier=supplier or None))


@frappe.whitelist(methods=["POST"])
def settle_internal(version):
	return respond(version, sourcing.settle_internal(version))
