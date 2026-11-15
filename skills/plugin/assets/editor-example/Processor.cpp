#include "ParameterControl.h"

// Optional gain/editor example. Copy with ParameterControl.h and the parent CMakeLists.
// Change product identity before installation. The plain parent starter stays transparent.
class AudioStudy final : public juce::AudioProcessor {
public:
    AudioStudy() : AudioProcessor(BusesProperties()
          .withInput("Input", juce::AudioChannelSet::stereo(), true)
          .withOutput("Output", juce::AudioChannelSet::stereo(), true)),
          parameters(*this, nullptr, "GainStudyState", layout()) {}
    static juce::AudioProcessorValueTreeState::ParameterLayout layout() {
        juce::AudioProcessorValueTreeState::ParameterLayout result;
        const auto attrs = juce::AudioParameterFloatAttributes().withLabel("dB")
            .withStringFromValueFunction([](float value, int) { return juce::String(value, 1); })
            .withValueFromStringFunction([](const juce::String& text) { return text.getFloatValue(); });
        result.add(std::make_unique<juce::AudioParameterFloat>(juce::ParameterID{"level", 1},
            "Level", juce::NormalisableRange<float>{-48, 6, 0.1f}, 0, attrs));
        return result;
    }
    const juce::String getName() const override { return JucePlugin_Name; }
    void prepareToPlay(double rate, int) override { gain.reset(rate, 0.02); reset(); }
    void reset() override { gain.setCurrentAndTargetValue(target()); }
    void releaseResources() override {}
    bool isBusesLayoutSupported(const BusesLayout& buses) const override {
        const auto output = buses.getMainOutputChannelSet();
        return (output == juce::AudioChannelSet::mono() || output == juce::AudioChannelSet::stereo())
            && buses.getMainInputChannelSet() == output;
    }
    void processBlock(juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midi) override {
        juce::ScopedNoDenormals noDenormals;
        gain.setTargetValue(target());
        for (int frame = 0; frame < buffer.getNumSamples(); ++frame) {
            const auto value = gain.getNextValue();
            for (int channel = 0; channel < buffer.getNumChannels(); ++channel)
                buffer.setSample(channel, frame, buffer.getSample(channel, frame) * value);
        }
        midi.clear();
    }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 0; }
    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram(int) override {}
    const juce::String getProgramName(int) override { return "Init"; }
    void changeProgramName(int, const juce::String&) override {}
    bool hasEditor() const override { return true; }
    class Editor final : public juce::AudioProcessorEditor {
    public:
        explicit Editor(AudioStudy& owner) : AudioProcessorEditor(owner),
              level(owner.parameters, "level", "Output level in decibels.") {
            setName("Gain study editor");
            heading.setText("Gain study", juce::dontSendNotification);
            heading.setFont(juce::FontOptions(28, juce::Font::bold));
            heading.setColour(juce::Label::textColourId, theme.ink);
            addAndMakeVisible(heading);
            hint.setText("OUTPUT LEVEL  /  Shift-drag to fine-adjust", juce::dontSendNotification);
            hint.setColour(juce::Label::textColourId, theme.muted);
            addAndMakeVisible(hint);
            addAndMakeVisible(level);
            setResizable(true, true);
            setResizeLimits(340, 340, 680, 600);
            setSize(400, 400);
        }
        void paint(juce::Graphics& graphics) override { graphics.fillAll(theme.background); }
        void resized() override {
            auto area = getLocalBounds().reduced(24);
            heading.setBounds(area.removeFromTop(42));
            hint.setBounds(area.removeFromTop(24));
            area.removeFromTop(12);
            level.setBounds(area.withSizeKeepingCentre(juce::jmin(260, area.getWidth()), area.getHeight()));
        }
    private:
        EditorExample::Theme theme;
        juce::Label heading, hint;
        EditorExample::ParameterControl level;
    };
    juce::AudioProcessorEditor* createEditor() override { return new Editor(*this); }
    void getStateInformation(juce::MemoryBlock& destination) override {
        copyXmlToBinary(*parameters.copyState().createXml(), destination);
    }
    void setStateInformation(const void* data, int bytes) override {
        const auto xml = getXmlFromBinary(data, bytes);
        if (xml && xml->hasTagName(parameters.state.getType()))
            parameters.replaceState(juce::ValueTree::fromXml(*xml));
    }
    juce::AudioProcessorValueTreeState parameters;
private:
    float target() const { return juce::Decibels::decibelsToGain(parameters.getRawParameterValue("level")->load()); }
    juce::SmoothedValue<float> gain;
};

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter() { return new AudioStudy; }
