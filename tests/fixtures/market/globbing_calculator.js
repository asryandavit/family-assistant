// Globbing calculator, sliced verbatim from https://am.globbing.com/build/js/app-1793261965033.js
// captured 2026-10-29 (Market watch P1). Constants, Calculator.calculate and getPricePerKg only.
const chargeableWeightTypeGross = 1;
const chargeableWeightTypeDimensional = 2;
const overDimensional = 1;
const measurementCm = 'cm';
const measurementInch = 'inch';
const measurementMeter = 'meter';
const measurementKg = 'kg';
const measurementLbs = 'lbs';
const inchToCmMultiplier = 2.54;
const meterToCmMultiplier = 100;
const lbsToKgMultiplier = 0.45359237;

function Calculator(form) {
    this.form = form;
    this.weight = this.form.find('.calculator-weight');
    this.priceInput = this.form.find('.calculator-price');
    this.currency = this.form.find('.calculator-currency');
    this.weigthMeasurement = this.form.find('.weight-measurement');
    this.range = this.form.find('.calculator-range');
    this.overDimensional = this.form.find('.over-dimensional');
    this.width = this.form.find('.calculator-width');
    this.height = this.form.find('.calculator-height');
    this.length = this.form.find('.calculator-length');
    this.measurement = this.form.find('.calculator-measurement');
    this.extraFeeBlock = this.form.find('.calculator__extra_fee-block');
    this.shippingCondition = {};
    this.selectedMembership = null;
}

Calculator.prototype.init = function () {
    this.initSlider();
    this.listenOverDimensionalChange();
    this.listenShippingConditionChange();
    this.listenExportShippingConditionChange();
    this.listenSourceWarehouseChange();
    this.listenSourceWarehouseTabChange();
    this.listenWeightChange();
    this.listenPriceInputChange();
    this.listenCurrencyChange();
    this.listenWeightMeasurementChange();
    this.listenWidthChange();
    this.listenHeightChange();
    this.listenLengthChange();
    this.listenMeasurementChange();
    this.listenOrderTypeChange();
};

Calculator.prototype.calculate = function () {
    let selectedCurrency = mainCurrency.id;
    let mainCurrencyRate = 1;
    let price = 0;
    let declarationPrice = this.priceInput.val();
    let weight = +this.weight.val();

    if (this.weigthMeasurement.val() === measurementLbs) {
        weight *= lbsToKgMultiplier;
    }

    if (weight <= 0) {
        this.setPrice(price);
        this.setShippingFee(price);
        this.setCustomsFee(price);
        return false;
    }

    let inputWeight = weight;

    if (declarationPrice > 0) {
        selectedCurrency = this.currency.val();

        if (typeof rates[selectedCurrency] != "undefined" && typeof rates[selectedCurrency]['bank_rate'] != "undefined") {
            mainCurrencyRate = rates[selectedCurrency]['bank_rate'];
        }

        declarationPrice = parseFloat(declarationPrice / mainCurrencyRate).toFixed(mainCurrency.amount_precision);
    }

    let isOverDimensional;
    let width = +this.width.val();
    let height = +this.height.val();
    let length = +this.length.val();

    if (this.measurement.val() === measurementInch) {
        width *= inchToCmMultiplier;
        height *= inchToCmMultiplier;
        length *= inchToCmMultiplier;
    }

    if (this.measurement.val() === measurementMeter) {
        width *= meterToCmMultiplier;
        height *= meterToCmMultiplier;
        length *= meterToCmMultiplier;
    }

    let dimensionalWeight = (width * height * length) / 5000;

    if (this.selectedMembership) {
        this.shippingCondition.min_weight = this.selectedMembership.min_weight;
        this.shippingCondition.divider = this.selectedMembership.divider;
        this.shippingCondition.step = this.selectedMembership.step;
        this.shippingCondition.price_per_kg = this.selectedMembership.show_price_per_kg ? this.selectedMembership.show_price_per_kg : this.selectedMembership.price_per_kg;
        this.shippingCondition.min_price_per_kg = this.selectedMembership.show_min_price_per_kg ? this.selectedMembership.show_min_price_per_kg : this.selectedMembership.min_price_per_kg;
        this.shippingCondition.chargeable_weight_type = this.selectedMembership.chargeable_weight_type;
        this.shippingCondition.over_dimensional = this.selectedMembership.over_dimensional;
        this.shippingCondition.dimensions_sum = this.selectedMembership.dimensions_sum;
        this.shippingCondition.greater_weight = this.selectedMembership.greater_weight;
        this.shippingCondition.over_dimensional_price_per_kg = this.selectedMembership.show_over_dimensional_price_per_kg ? this.selectedMembership.show_over_dimensional_price_per_kg : this.selectedMembership.over_dimensional_price_per_kg;
        this.shippingCondition.additional_configs = this.selectedMembership.additional_configs;
    }

    if (this.shippingCondition.chargeable_weight_type === chargeableWeightTypeDimensional ||
        (
            isOverDimensional = this.shippingCondition.over_dimensional === overDimensional &&
                (width + height + length) >= this.shippingCondition.dimensions_sum &&
                (dimensionalWeight / weight) > this.shippingCondition.greater_weight
        ) ||
        // GEN-3115: Compare Gross and Dimensions — charge MAX(gross, dimensional); price stays by the over-dim rule
        this.shippingCondition.compare_gross_and_dimensions === 1
    ) {
        weight = weight > dimensionalWeight ? weight : dimensionalWeight;
    }

    weight = weight < this.shippingCondition.min_weight ? this.shippingCondition.min_weight : weight;
    weight = Math.round(weight * 1000);
    let divider = this.shippingCondition.divider * 1000;
    let step = this.shippingCondition.step * 1000;

    weight = parseInt(weight % step) < divider ?
        (parseInt(weight / step) * step) :
        ((parseInt(weight / step) + 1) * step);

    let pricePerKg = isOverDimensional ? this.shippingCondition.over_dimensional_price_per_kg :
        this.getPricePerKg(this.shippingCondition, weight);

    price = parseFloat(weight / 1000) * pricePerKg;
    price = price < this.shippingCondition.min_price_per_kg ? this.shippingCondition.min_price_per_kg : price;
    if (this.shippingCondition.extra_fee !== null) {
        price += this.shippingCondition.extra_fee;
    }
    price = Math.round(price * 100) / 100;
    if (calculatorLoyaltyMemberships.length !== 0 && !this.selectedMembership) {
        this.form.find('.loyalty_membership-box').addClass('form-error');
        price = 0;
    }

    let customsFeeTotal = 0, customsFeeByWeight = 0, customsFeeByPrice = 0;

    // const weightInKg = weight / 1000
    const inputWeightInKg = inputWeight

    if (declarationPrice > customsLimitConverted) {
        customsFeeByPrice = (declarationPrice - customsLimitConverted) * 0.15;
    }

    if (inputWeightInKg > customsWeightLimit) {
        customsFeeByWeight = 2 * (inputWeightInKg - customsWeightLimit) * currencyEuroRate;
    }

    customsFeeTotal = this.shippingCondition.customs_method !== 0
        ? Math.round((customsFeeByPrice >= customsFeeByWeight ? customsFeeByPrice : customsFeeByWeight) * 100) / 100
        : 0;

    if (this.weight.val() <= 0) {
        price = 0;
    }

    this.setPrice(Math.round((price + customsFeeTotal) * 100) / 100);
    this.setShippingFee(price);
    this.setCustomsFee(customsFeeTotal);
};
Calculator.prototype.getPricePerKg = function (shippingCondition, weight) {
    weight = parseFloat(weight / 1000);
    let pricePerKg = shippingCondition.price_per_kg;
    let additionalConfigs = JSON.parse(shippingCondition.additional_configs);
    if (additionalConfigs != null) {
        additionalConfigs.sort(function (a, b) {
            return b['weight'] - a['weight'];
        });

        for (let i = 0; i < additionalConfigs.length; i++) {
            let config = additionalConfigs[i];
            if (typeof (config.source) !== 'undefined' && config.source !== 'globbing') {
                continue;
            }
            if (weight >= config.weight) {
                 pricePerKg = config.price;
                 break;
            }
        }
    }

    return pricePerKg;
};

