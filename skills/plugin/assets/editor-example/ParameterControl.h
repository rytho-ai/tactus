#pragma once
#include <juce_audio_utils/juce_audio_utils.h>

// An editable mechanism example. Own the actual visual direction in each project.
namespace EditorExample {
struct Theme {
    juce::Colour background {0xfff2eee5}, surface {0xffe5dfd3};
    juce::Colour ink {0xff23313a}, muted {0xff59666b}, accent {0xffa84427};
};

class DialLook final : public juce::LookAndFeel_V4 {
public:
    explicit DialLook(Theme colors) : theme(colors) {
        setColour(juce::Slider::textBoxTextColourId, theme.ink);
        setColour(juce::Slider::textBoxBackgroundColourId, theme.background);
        setColour(juce::Slider::textBoxOutlineColourId, theme.muted);
        setColour(juce::TextButton::buttonColourId, theme.surface);
        setColour(juce::TextButton::textColourOffId, theme.ink);
        setColour(juce::Label::textColourId, theme.ink);
    }
    void drawRotarySlider(juce::Graphics& g, int x, int y, int width, int height,
                          float position, float start, float end, juce::Slider& slider) override {
        const auto area = juce::Rectangle<float>(float(x), float(y), float(width), float(height)).reduced(7);
        const auto radius = juce::jmax(1.0f, juce::jmin(area.getWidth(), area.getHeight()) * 0.5f - 3);
        const auto centre = area.getCentre();
        const auto angle = start + position * (end - start);
        juce::Path rail, active;
        rail.addCentredArc(centre.x, centre.y, radius, radius, 0, start, end, true);
        active.addCentredArc(centre.x, centre.y, radius, radius, 0, start, angle, true);
        g.setColour(theme.surface);
        g.strokePath(rail, juce::PathStrokeType(5));
        g.setColour(slider.isEnabled() ? theme.accent : theme.muted);
        g.strokePath(active, juce::PathStrokeType(5));
        const auto pointer = centre.getPointOnCircumference(radius * 0.75f, angle);
        g.drawLine({centre, pointer}, 3);
        g.setColour(theme.ink);
        g.fillEllipse(centre.x - 3, centre.y - 3, 6, 6);
        if (slider.hasKeyboardFocus(true)) {
            g.setColour(theme.accent);
            g.drawRoundedRectangle(area.expanded(2), 5, 1.5f);
        }
    }
private:
    Theme theme;
};

class FineSlider final : public juce::Slider {
public:
    void mouseDown(const juce::MouseEvent& event) override {
        setMouseDragSensitivity(event.mods.isShiftDown() ? 2000 : 200);
        juce::Slider::mouseDown(event);
    }
    void mouseUp(const juce::MouseEvent& event) override {
        juce::Slider::mouseUp(event);
        setMouseDragSensitivity(200);
    }
};

class ParameterControl final : public juce::Component {
public:
    ParameterControl(juce::AudioProcessorValueTreeState& state, const juce::String& id,
                     const juce::String& help, Theme colors = {})
        : parameter(*state.getParameter(id)), look(colors), theme(colors) {
        setName(id);
        setFocusContainerType(juce::Component::FocusContainerType::focusContainer);
        title.setText(parameter.getName(64), juce::dontSendNotification);
        title.setJustificationType(juce::Justification::centred);
        title.setFont(juce::FontOptions(15, juce::Font::bold));
        title.setColour(juce::Label::textColourId, theme.ink);
        addAndMakeVisible(title);
        slider.setLookAndFeel(&look);
        slider.setName(id);
        slider.setTitle(parameter.getName(64));
        slider.setDescription(help);
        slider.setHelpText("Drag vertically; hold Shift before dragging to fine-adjust. "
                           "Edit the value below, or double-click the dial to reset.");
        slider.setTooltip(help + "  Shift-drag: fine adjustment. Double-click dial: factory default.");
        slider.setSliderStyle(juce::Slider::RotaryVerticalDrag);
        slider.setTextBoxStyle(juce::Slider::TextBoxBelow, false, 112, 28);
        slider.setWantsKeyboardFocus(true);
        slider.setExplicitFocusOrder(1);
        addAndMakeVisible(slider);
        attachment = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment>(state, id, slider);
        // The attachment owns range, parser, formatter, factory default and gestures.
        if (parameter.getLabel().isNotEmpty()) slider.setTextValueSuffix(" " + parameter.getLabel());
        reset.setLookAndFeel(&look);
        reset.setButtonText("Reset");
        reset.setTitle("Reset " + parameter.getName(64));
        reset.setHelpText("Restore this parameter's factory default.");
        reset.setWantsKeyboardFocus(true);
        reset.setExplicitFocusOrder(2);
        reset.onClick = [this] { resetToDefault(); };
        addAndMakeVisible(reset);
    }
    ~ParameterControl() override {
        slider.setLookAndFeel(nullptr);
        reset.setLookAndFeel(nullptr);
    }
    void resetToDefault() {
        parameter.beginChangeGesture();
        parameter.setValueNotifyingHost(parameter.getDefaultValue());
        parameter.endChangeGesture();
    }
    void resized() override {
        auto bounds = getLocalBounds();
        title.setBounds(bounds.removeFromTop(26));
        reset.setBounds(bounds.removeFromBottom(28).withSizeKeepingCentre(72, 28));
        bounds.removeFromBottom(8);
        slider.setBounds(bounds);
    }
    FineSlider slider;
    juce::TextButton reset;
private:
    juce::RangedAudioParameter& parameter;
    DialLook look;
    Theme theme;
    juce::Label title;
    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> attachment;
};
} // namespace EditorExample
