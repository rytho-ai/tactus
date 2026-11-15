cmake_minimum_required(VERSION 3.22)
project(AudioStudy VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(JUCE_SOURCE_DIR "" CACHE PATH "Path to the project's pinned JUCE checkout")
if(JUCE_SOURCE_DIR)
    add_subdirectory("${JUCE_SOURCE_DIR}" "${CMAKE_BINARY_DIR}/JUCE")
else()
    find_package(JUCE CONFIG REQUIRED)
endif()

# Choose the product identity once, before using it outside an isolated test project.
# Keep it stable after release. Parameter IDs/order are independent of these codes.
juce_add_plugin(AudioPlugin
    COMPANY_NAME "Local Audio"
    BUNDLE_ID "local.audio.study"
    PLUGIN_MANUFACTURER_CODE Locl
    PLUGIN_CODE Aust
    PRODUCT_NAME "Audio Study"
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT FALSE
    FORMATS VST3 Standalone
    COPY_PLUGIN_AFTER_BUILD FALSE)

target_sources(AudioPlugin PRIVATE Processor.cpp)
target_compile_definitions(AudioPlugin PRIVATE
    JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0 JUCE_VST3_CAN_REPLACE_VST2=0)
target_link_libraries(AudioPlugin PRIVATE juce::juce_audio_utils
    PUBLIC juce::juce_recommended_config_flags juce::juce_recommended_warning_flags)

# Seal the completed local-development bundle after JUCE generates moduleinfo.json.
# Keep installation explicit; never overwrite a binary that a host still has loaded.
if(APPLE)
    foreach(format VST3 Standalone)
        get_target_property(bundle AudioPlugin_${format} JUCE_PLUGIN_ARTEFACT_FILE)
        add_custom_command(TARGET AudioPlugin_${format} POST_BUILD
            COMMAND /usr/bin/codesign --force --sign - "${bundle}"
            COMMAND /usr/bin/codesign --verify --strict "${bundle}"
            VERBATIM)
    endforeach()
endif()
