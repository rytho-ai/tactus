#include <juce_audio_utils/juce_audio_utils.h>

// A transparent starting point. Own the actual processor, parameters and editor here.
class AudioStudy final : public juce::AudioProcessor {
public:
    AudioStudy()
        : AudioProcessor(BusesProperties()
              .withInput("Input", juce::AudioChannelSet::stereo(), true)
              .withOutput("Output", juce::AudioChannelSet::stereo(), true)) {}

    const juce::String getName() const override { return JucePlugin_Name; }
    void prepareToPlay(double, int) override {}
    void releaseResources() override {}
    bool isBusesLayoutSupported(const BusesLayout& layout) const override {
        const auto output = layout.getMainOutputChannelSet();
        return (output == juce::AudioChannelSet::mono()
                || output == juce::AudioChannelSet::stereo())
            && layout.getMainInputChannelSet() == output;
    }
    void processBlock(juce::AudioBuffer<float>&, juce::MidiBuffer& midi) override {
        juce::ScopedNoDenormals noDenormals;
        midi.clear();
    }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 0; }
    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram(int) override {}
    const juce::String getProgramName(int) override { return {}; }
    void changeProgramName(int, const juce::String&) override {}
    bool hasEditor() const override { return false; }
    juce::AudioProcessorEditor* createEditor() override { return nullptr; }
    void getStateInformation(juce::MemoryBlock& state) override { state.reset(); }
    void setStateInformation(const void*, int) override {}
};

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter() { return new AudioStudy; }
